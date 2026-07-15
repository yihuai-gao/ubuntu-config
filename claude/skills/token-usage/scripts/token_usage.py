#!/usr/bin/env python3
"""Sum Claude Code token usage and API-equivalent cost across all session transcripts.

Scans ~/.claude/projects/*/*.jsonl, dedupes streamed entries by message id,
filters by timestamp, aggregates per model, and prices with a built-in table.

Run with /usr/bin/python3 (stdlib only, no venv needed).
"""

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
CONFIG_PATH = os.path.expanduser("~/.claude/skills/token-usage/reset_config.json")

# USD per million tokens (base input / output). Cache rates are derived:
# read = 0.1x input, 5m write = 1.25x input, 1h write = 2x input.
# Source: claude-api skill pricing table (cached 2026-06).
PRICING = {
    "claude-fable-5": (10.0, 50.0),
    "claude-mythos-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def lookup_pricing(model):
    """Prefix match so date-suffixed ids (claude-haiku-4-5-20251001) resolve."""
    for key in sorted(PRICING, key=len, reverse=True):
        if model == key or model.startswith(key + "-"):
            return PRICING[key]
    return None


def parse_since(text):
    """Accept relative ('7d', '36h', '2w', '90min') or ISO datetime (naive = local tz)."""
    import re

    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(min|h|d|w)", text.strip())
    if m:
        value = float(m.group(1))
        unit = {"min": "minutes", "h": "hours", "d": "days", "w": "weeks"}[m.group(2)]
        return datetime.now(timezone.utc) - timedelta(**{unit: value})
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.astimezone()  # interpret naive input as local time
    return dt.astimezone(timezone.utc)


def since_from_config():
    """Compute the most recent reset boundary from the stored anchor + period."""
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    anchor = datetime.fromisoformat(cfg["anchor"]).astimezone(timezone.utc)
    period = timedelta(hours=cfg.get("period_hours", 168))
    now = datetime.now(timezone.utc)
    if anchor > now:
        return anchor - period * ((anchor - now) // period + 1)
    return anchor + period * ((now - anchor) // period)


def save_config(anchor_text, period_hours):
    anchor = parse_since(anchor_text)
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump({"anchor": anchor.isoformat(), "period_hours": period_hours}, f, indent=2)
    print(f"Saved reset anchor {anchor.isoformat()} with period {period_hours}h to {CONFIG_PATH}")


def session_label(path, max_len=60):
    """Human-readable session label: the first real user message (or /command name)."""
    import re

    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") == "summary" and d.get("summary"):
                    return d["summary"][:max_len]
                if d.get("type") != "user":
                    continue
                content = (d.get("message") or {}).get("content")
                if isinstance(content, list):
                    content = next((b.get("text", "") for b in content
                                    if isinstance(b, dict) and b.get("type") == "text"), "")
                if not isinstance(content, str) or not content.strip():
                    continue
                cmd = re.search(r"<command-name>(.*?)</command-name>", content)
                if cmd:
                    return cmd.group(1).strip()[:max_len]
                if content.startswith("<") and "system-reminder" in content[:50]:
                    continue
                return " ".join(content.split())[:max_len]
    except OSError:
        pass
    return "(no user message)"


def scan(since):
    stats = defaultdict(lambda: defaultdict(int))  # model -> counters
    projects = defaultdict(lambda: defaultdict(int))  # project -> counters (tokens only)
    per_session = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # path -> model -> counters
    session_times = {}  # path -> [earliest, latest]
    seen = set()
    sessions = set()
    earliest, latest = None, None

    for path in glob.glob(os.path.join(PROJECTS_DIR, "*", "*.jsonl")):
        project = os.path.basename(os.path.dirname(path))
        try:
            fh = open(path, errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") != "assistant":
                    continue
                msg = d.get("message") or {}
                usage = msg.get("usage")
                model = msg.get("model")
                if not usage or not model or model == "<synthetic>":
                    continue
                ts_text = d.get("timestamp")
                if not ts_text:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_text.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts < since:
                    continue
                # Streamed responses are written as multiple entries sharing one
                # message id and identical usage — count each API response once.
                key = msg.get("id") or d.get("requestId")
                if key in seen:
                    continue
                seen.add(key)

                cc = usage.get("cache_creation") or {}
                write_1h = cc.get("ephemeral_1h_input_tokens", 0)
                write_5m = cc.get("ephemeral_5m_input_tokens")
                if write_5m is None:
                    # No breakdown: attribute all cache writes to the 5m tier.
                    write_5m = usage.get("cache_creation_input_tokens", 0) - write_1h

                for s in (stats[model], per_session[path][model]):
                    s["requests"] += 1
                    s["input"] += usage.get("input_tokens", 0)
                    s["output"] += usage.get("output_tokens", 0)
                    s["cache_read"] += usage.get("cache_read_input_tokens", 0)
                    s["cache_write_5m"] += write_5m
                    s["cache_write_1h"] += write_1h

                t = session_times.setdefault(path, [ts, ts])
                t[0] = min(t[0], ts)
                t[1] = max(t[1], ts)

                p = projects[project]
                p["requests"] += 1
                for k in ("input", "output", "cache_read"):
                    p[k] = p.get(k, 0)
                p["input"] += usage.get("input_tokens", 0)
                p["output"] += usage.get("output_tokens", 0)
                p["cache_read"] += usage.get("cache_read_input_tokens", 0)
                p["cache_write"] += write_5m + write_1h

                sessions.add(path)
                earliest = ts if earliest is None or ts < earliest else earliest
                latest = ts if latest is None or ts > latest else latest

    return stats, projects, per_session, session_times, sessions, earliest, latest


def cost_of(model, s):
    rates = lookup_pricing(model)
    if rates is None:
        return None
    inp, out = rates
    per = 1_000_000
    return (
        s["input"] / per * inp
        + s["output"] / per * out
        + s["cache_read"] / per * inp * 0.1
        + s["cache_write_5m"] / per * inp * 1.25
        + s["cache_write_1h"] / per * inp * 2.0
    )


def fmt(n):
    return f"{n:,}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", help="ISO datetime or relative (7d, 36h, 2w). "
                    "Omit to use the stored reset anchor.")
    ap.add_argument("--set-reset", metavar="WHEN",
                    help="Store a reset anchor (ISO datetime) for future runs, then exit.")
    ap.add_argument("--period-hours", type=int, default=168,
                    help="Reset cadence in hours for --set-reset (default 168 = weekly).")
    ap.add_argument("--by-project", action="store_true", help="Also show per-project token totals.")
    ap.add_argument("--by-session", action=argparse.BooleanOptionalAction, default=True,
                    help="List each session with its cost (default: on; "
                         "use --no-by-session to hide).")
    ap.add_argument("--sort", choices=["cost", "time"], default="cost",
                    help="Sort order for --by-session (default: cost, descending; "
                         "time = chronological by session start).")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = ap.parse_args()

    if args.set_reset:
        save_config(args.set_reset, args.period_hours)
        return

    if args.since:
        since = parse_since(args.since)
        since_source = f"--since {args.since}"
    else:
        since = since_from_config()
        since_source = "stored reset anchor"
        if since is None:
            sys.exit("No --since given and no reset anchor stored.\n"
                     "Either pass --since (e.g. --since 7d or --since 2026-07-09T18:00) or store\n"
                     "your credit reset time once:  --set-reset '2026-07-09T18:00' --period-hours 168\n"
                     "(Claude Code shows the reset time in /usage.)")

    stats, projects, per_session, session_times, sessions, earliest, latest = scan(since)

    def session_rows():
        rows = []
        for path, models in per_session.items():
            cost = 0.0
            agg = defaultdict(int)
            priced = True
            for model, s in models.items():
                c = cost_of(model, s)
                if c is None:
                    priced = False
                else:
                    cost += c
                for k, v in s.items():
                    agg[k] += v
            rows.append((path, cost, priced, agg))
        if args.sort == "time":
            rows.sort(key=lambda r: session_times[r[0]][0])
        else:
            rows.sort(key=lambda r: -r[1])
        return rows

    total_cost = 0.0
    unknown_models = []
    rows = []
    totals = defaultdict(int)
    for model, s in sorted(stats.items(), key=lambda kv: -(cost_of(*kv) or 0)):
        c = cost_of(model, s)
        if c is None:
            unknown_models.append(model)
        else:
            total_cost += c
        rows.append((model, s, c))
        for k in ("requests", "input", "output", "cache_read", "cache_write_5m", "cache_write_1h"):
            totals[k] += s[k]

    if args.json:
        print(json.dumps({
            "since": since.isoformat(),
            "since_source": since_source,
            "sessions": len(sessions),
            "models": {m: {**s, "cost_usd": c} for m, s, c in rows},
            "totals": {**totals, "cost_usd": round(total_cost, 2)},
            "projects": {p: dict(v) for p, v in projects.items()} if args.by_project else None,
            "session_list": [{
                "path": path,
                "label": session_label(path),
                "project": os.path.basename(os.path.dirname(path)),
                "start": session_times[path][0].isoformat(),
                "end": session_times[path][1].isoformat(),
                "cost_usd": round(cost, 2),
                "fully_priced": priced,
                **{k: agg[k] for k in ("requests", "input", "output", "cache_read",
                                       "cache_write_5m", "cache_write_1h")},
            } for path, cost, priced, agg in session_rows()] if args.by_session else None,
            "unknown_models": unknown_models,
        }, indent=2))
        return

    print(f"Window: since {since.astimezone().strftime('%Y-%m-%d %H:%M %Z')} ({since_source})")
    if earliest:
        print(f"Matched: {totals['requests']:,} API responses in {len(sessions)} session files "
              f"({earliest.astimezone():%m-%d %H:%M} .. {latest.astimezone():%m-%d %H:%M})")
    else:
        print("No usage entries found in this window.")
        return

    header = f"{'model':<22}{'reqs':>7}{'input':>12}{'output':>12}{'cache read':>14}{'cache w5m':>12}{'cache w1h':>12}{'cost USD':>11}"
    print("\n" + header)
    print("-" * len(header))
    for model, s, c in rows:
        cost_text = f"${c:,.2f}" if c is not None else "unknown"
        print(f"{model:<22}{fmt(s['requests']):>7}{fmt(s['input']):>12}{fmt(s['output']):>12}"
              f"{fmt(s['cache_read']):>14}{fmt(s['cache_write_5m']):>12}{fmt(s['cache_write_1h']):>12}{cost_text:>11}")
    print("-" * len(header))
    print(f"{'TOTAL':<22}{fmt(totals['requests']):>7}{fmt(totals['input']):>12}{fmt(totals['output']):>12}"
          f"{fmt(totals['cache_read']):>14}{fmt(totals['cache_write_5m']):>12}{fmt(totals['cache_write_1h']):>12}"
          f"{'$' + format(total_cost, ',.2f'):>11}")

    if unknown_models:
        print(f"\nWARNING: no pricing for {', '.join(unknown_models)} — tokens counted, cost excluded.")

    if args.by_project:
        print(f"\n{'project':<64}{'reqs':>7}{'output':>12}{'cache read':>14}")
        for p, v in sorted(projects.items(), key=lambda kv: -kv[1]["output"]):
            print(f"{p[:63]:<64}{fmt(v['requests']):>7}{fmt(v['output']):>12}{fmt(v['cache_read']):>14}")

    if args.by_session:
        header = f"{'start':<12}{'cost USD':>10}{'reqs':>6}{'output':>10}{'cache read':>14}  {'session':<62}"
        print("\n" + header)
        print("-" * len(header))
        for path, cost, priced, agg in session_rows():
            start = session_times[path][0].astimezone().strftime("%m-%d %H:%M")
            cost_text = f"${cost:,.2f}" + ("" if priced else "+")
            print(f"{start:<12}{cost_text:>10}{fmt(agg['requests']):>6}{fmt(agg['output']):>10}"
                  f"{fmt(agg['cache_read']):>14}  {session_label(path):<62}")
        print("(+ = session includes a model with unknown pricing; cost is a lower bound)"
              if any(not priced for _, _, priced, _ in session_rows()) else "", end="")


if __name__ == "__main__":
    main()
