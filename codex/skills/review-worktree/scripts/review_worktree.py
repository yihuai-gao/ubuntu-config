#!/usr/bin/env python3
"""Read-only Git worktree triage using local Codex session evidence."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sqlite3
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def git(path: Path, *args: str, allowed: tuple[int, ...] = (0,)) -> str:
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(path), *args],
        capture_output=True,
        text=True,
        errors="surrogateescape",
        timeout=60,
    )
    if result.returncode not in allowed:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def list_worktrees(workspace: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for field in git(workspace, "worktree", "list", "--porcelain", "-z").split("\0"):
        if not field:
            if current:
                rows.append(current)
                current = {}
            continue
        key, _, value = field.partition(" ")
        if key == "worktree":
            current = {"path": str(Path(value).resolve()), "branch": None}
        elif key == "branch":
            current[key] = value.removeprefix("refs/heads/")
        else:
            current[key] = value or True
    if current:
        rows.append(current)
    if not rows or rows[0].get("bare"):
        raise RuntimeError("A non-bare main worktree is required for comparison")
    return rows


def status_paths(raw: str) -> list[tuple[str, str]]:
    """Retain both sides of renames: a rename also removes the source path."""
    fields = iter(raw.split("\0"))
    result: list[tuple[str, str]] = []
    for field in fields:
        if not field:
            continue
        status, path = field[:2], field[3:]
        result.append((status, path))
        if "R" in status or "C" in status:
            original = next(fields)
            if "R" in status:
                result.append(("D ", original))
    return result


def equal_files(left: Path, right: Path) -> bool:
    """Compare bytes, executable mode, symlinks, and missing paths separately."""
    if left.is_symlink() or right.is_symlink():
        return (
            left.is_symlink()
            and right.is_symlink()
            and os.readlink(left) == os.readlink(right)
        )
    if not left.exists() or not right.exists():
        return not left.exists() and not right.exists()
    if not left.is_file() or not right.is_file():
        return False
    if left.stat().st_mode & 0o111 != right.stat().st_mode & 0o111:
        return False
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as a, right.open("rb") as b:
        while chunk := a.read(1024 * 1024):
            if chunk != b.read(len(chunk)):
                return False
        return not b.read(1)


def tree_entries(
    path: Path, revision: str, names: list[str]
) -> dict[str, tuple[str, str]]:
    """Read committed modes and blob IDs without consulting the working copy."""
    if not names:
        return {}
    result = {}
    for entry in git(path, "ls-tree", "-r", "-z", revision, "--", *names).split("\0"):
        if entry:
            metadata, name = entry.split("\t", 1)
            mode, _, oid = metadata.split()
            result[name] = (mode, oid)
    return result


def file_entry(path: Path, name: str) -> tuple[str, str] | None:
    target = path / name
    if target.is_symlink():
        data = os.fsencode(os.readlink(target))
        mode = "120000"
    elif not target.exists():
        return None
    elif target.is_file():
        mode = "100755" if target.stat().st_mode & 0o111 else "100644"
        return mode, git(path, "hash-object", "--no-filters", "--", name).strip()
    else:
        return ("directory", "")  # A directory is not an ordinary committed blob.
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(path), "hash-object", "--stdin"],
        input=data,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return mode, result.stdout.decode().strip()


def compare_changes(
    path: Path, main: dict[str, Any], changes: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    names = list(dict.fromkeys(name for _, name in changes))
    committed = tree_entries(Path(main["path"]), main["HEAD"], names)
    index: dict[str, tuple[str, str]] = {}
    conflicts: set[str] = set()
    if names:
        for entry in git(path, "ls-files", "--stage", "-z", "--", *names).split("\0"):
            if entry:
                metadata, name = entry.split("\t", 1)
                mode, oid, stage = metadata.split()
                if stage != "0":
                    conflicts.add(name)
                index[name] = (mode, oid)
    return [
        {
            "path": name,
            "status": status,
            "matches_main_head": file_entry(path, name) == committed.get(name),
            "matches_main_worktree": equal_files(
                path / name, Path(main["path"]) / name
            ),
            "staged": status[0] not in " ?",
            "index_matches_main_head": name not in conflicts
            and index.get(name) == committed.get(name),
            "index_conflict": name in conflicts,
        }
        for status, name in changes
    ]


def git_facts(row: dict[str, Any], main: dict[str, Any]) -> dict[str, Any]:
    path = Path(row["path"])
    facts = {**row, "changes": [], "ignored": [], "unlanded": [], "last_edit": 0.0}
    if not path.is_dir():
        return {**facts, "missing": True}
    try:
        status = git(
            path,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
        changes = status_paths(status)
        ignored = git(
            path,
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--directory",
            "-z",
        )
        ancestry = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-C",
                str(path),
                "merge-base",
                "--is-ancestor",
                "HEAD",
                main["HEAD"],
            ],
            capture_output=True,
            timeout=60,
        )
        if ancestry.returncode not in (0, 1):
            raise RuntimeError(ancestry.stderr.decode(errors="replace"))
        ahead, behind = git(
            path, "rev-list", "--left-right", "--count", f"HEAD...{main['HEAD']}"
        ).split()
        cherry = git(path, "cherry", main["HEAD"], "HEAD") if int(ahead) else ""
        edits = []
        for _, name in changes:
            target = path / name
            try:
                edits.append(target.lstat().st_mtime)
            except FileNotFoundError:
                pass
        last_file_edit = max(edits, default=0.0)
        last_commit = float(git(path, "log", "-1", "--format=%ct").strip())
        reflog = git(path, "reflog", "-1", "--format=%gD", "--date=unix").strip()
        last_checkout = (
            float(reflog.partition("@{")[2].rstrip("}")) if "@{" in reflog else 0.0
        )
        comparison = compare_changes(path, main, changes)
        if changes:
            # Index/reflog stamps cover staged deletions, which have no file mtime.
            for rel in ("index", "logs/HEAD"):
                stamp = Path(git(path, "rev-parse", "--git-path", rel).strip())
                stamp = stamp if stamp.is_absolute() else path / stamp
                if stamp.exists():
                    edits.append(stamp.stat().st_mtime)
        facts.update(
            changes=[{"status": status, "path": name} for status, name in changes],
            ignored=[name for name in ignored.split("\0") if name],
            unlanded=[c["path"] for c in comparison if not c["matches_main_head"]],
            staged_unlanded=[
                c["path"]
                for c in comparison
                if c["staged"] and not c["index_matches_main_head"]
            ],
            content_comparison=comparison,
            ancestor=ancestry.returncode == 0,
            ahead=int(ahead),
            behind=int(behind),
            unique_patches=sum(line.startswith("+") for line in cherry.splitlines()),
            last_edit=max(edits, default=0.0),
            last_file_edit=last_file_edit,
            last_commit=last_commit,
            last_checkout=last_checkout,
            last_content_update=max(last_file_edit, last_commit),
            submodules=git(path, "submodule", "status", "--recursive").splitlines(),
        )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        facts["error"] = str(exc)
    return facts


def timestamp(value: str | None) -> float:
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def loaded_state(home: Path, sid: str) -> str:
    """Probe an existing writer lock without creating a file or claiming liveness."""
    lock = home / "thread-writer-locks" / f"{sid}.lock"
    try:
        with lock.open("rb") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return "loaded"
            fcntl.flock(handle, fcntl.LOCK_UN)
            return "not loaded"
    except OSError:
        return "unknown"


def session_titles(home: Path, warnings: list[str]) -> dict[str, str]:
    titles: dict[str, str] = {}
    try:
        index = home / "session_index.jsonl"
        if index.exists():
            for line in index.read_text().splitlines():
                try:
                    row = json.loads(line)
                    titles[row["id"]] = row.get("thread_name", "")
                except (KeyError, TypeError, json.JSONDecodeError):
                    continue
        databases = sorted(
            home.glob("state_*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if databases:
            with sqlite3.connect(
                databases[0].as_uri() + "?mode=ro", uri=True
            ) as connection:
                titles.update(connection.execute("SELECT id, title FROM threads"))
    except (OSError, sqlite3.Error) as exc:
        warnings.append(f"Some session titles are unavailable: {exc}")
    return titles


def scan_sessions(
    home: Path, paths: list[str], exclude: set[str]
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Associate cwd and tool-input evidence, never quoted inventory output."""
    warnings: list[str] = []
    titles = session_titles(home, warnings)
    matches: dict[str, list[dict[str, Any]]] = {path: [] for path in paths}
    patterns = {
        path: re.compile(re.escape(path) + r"(?=$|[/\s\"'`,;)}\]])") for path in paths
    }
    found = False
    for root in (home / "sessions", home / "archived_sessions"):
        if not root.exists():
            continue
        for rollout in root.rglob("*.jsonl"):
            found = True
            sid = ""
            cwd = ""
            associations: dict[str, dict[str, Any]] = {}
            messages: deque[dict[str, str]] = deque(maxlen=12)
            pending: set[str] = set()
            last_event = "unknown"
            last_record = 0.0
            try:
                with rollout.open(encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        # Skip large reasoning/output records before JSON parsing.
                        if not any(
                            tag in line[:180]
                            for tag in (
                                '"session_meta"',
                                '"turn_context"',
                                '"event_msg"',
                                '"response_item"',
                            )
                        ):
                            continue
                        if '"response_item"' in line[:180] and not any(
                            tag in line[:350]
                            for tag in ('"function_call"', '"custom_tool_call"')
                        ):
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue  # A running session may have a partial final record.
                        payload = event.get("payload", {})
                        kind = event.get("type")
                        when = timestamp(event.get("timestamp"))
                        last_record = max(last_record, when)
                        evidence: dict[str, str] = {}
                        if kind == "session_meta":
                            sid = payload.get("id", "")
                            if sid in exclude:
                                break
                            # Startup cwd alone is not evidence of work.
                        elif kind == "turn_context":
                            cwd = str(Path(payload.get("cwd", "/")).resolve())
                            for path in paths:
                                if cwd == path or cwd.startswith(path + "/"):
                                    evidence[path] = "turn cwd"
                        elif kind == "response_item":
                            tool_input = payload.get(
                                "arguments", payload.get("input", "")
                            )
                            if not isinstance(tool_input, str):
                                continue
                            if (
                                "review_worktree.py" in tool_input
                                or "git worktree list" in tool_input
                            ):
                                continue
                            for path, pattern in patterns.items():
                                if pattern.search(tool_input):
                                    evidence[path] = "tool input"
                            # An explicit execution cwd is stronger evidence than a path mentioned in a command.
                            try:
                                arguments = json.loads(tool_input)
                            except json.JSONDecodeError:
                                arguments = {}
                            execution_cwd = (
                                arguments.get("workdir", arguments.get("cwd", ""))
                                if isinstance(arguments, dict)
                                else ""
                            )
                            if isinstance(execution_cwd, str) and execution_cwd:
                                for path in paths:
                                    if (
                                        execution_cwd == path
                                        or execution_cwd.startswith(path + "/")
                                    ):
                                        evidence[path] = "execution cwd"
                            for path in paths:
                                if cwd == path or cwd.startswith(path + "/"):
                                    if evidence.get(path) != "execution cwd":
                                        evidence[path] = "tool cwd"
                        elif kind == "event_msg":
                            event_type = payload.get("type", "")
                            turn = payload.get("turn_id", "legacy")
                            if event_type == "task_started":
                                pending.add(turn)
                                last_event = "unfinished turn"
                            elif event_type in (
                                "task_complete",
                                "turn_aborted",
                                "task_failed",
                            ):
                                pending.discard(turn)
                                last_event = event_type
                            elif event_type in ("user_message", "agent_message"):
                                message = payload.get("message", "")
                                if isinstance(message, str) and not message.startswith(
                                    "<"
                                ):
                                    messages.append(
                                        {"role": event_type, "text": message[:2000]}
                                    )
                            if event_type in ("task_complete", "agent_message"):
                                for path in associations:
                                    if cwd == path or cwd.startswith(path + "/"):
                                        evidence[path] = associations[path]["evidence"]
                        for path, why in evidence.items():
                            previous = associations.get(path, {})
                            owned = why in {"turn cwd", "tool cwd", "execution cwd"}
                            associations[path] = {
                                "last_used": when,
                                "evidence": why,
                                "last_workspace_use": when
                                if owned
                                else previous.get("last_workspace_use", 0.0),
                                "last_reference": when
                                if not owned
                                else previous.get("last_reference", 0.0),
                            }
            except OSError as exc:
                warnings.append(f"Cannot read {rollout}: {exc}")
                continue
            if not sid or sid in exclude:
                continue
            state = loaded_state(home, sid)
            for path, evidence in associations.items():
                matches[path].append(
                    {
                        "id": sid,
                        "title": titles.get(sid, ""),
                        "rollout": str(rollout),
                        "loaded": state,
                        "last_event": "unfinished turn" if pending else last_event,
                        "last_record": last_record,
                        "current_cwd": cwd,
                        **evidence,
                        "messages": list(messages),
                    }
                )
    if not found:
        warnings.append(
            f"No Codex rollout files found under {home}; session ownership is unknown"
        )
    for sessions in matches.values():
        # Multiple rollout files can describe one thread; do not count it repeatedly or prefer stale turn state.
        grouped: dict[str, list[dict[str, Any]]] = {}
        for session in sessions:
            grouped.setdefault(session["id"], []).append(session)
        sessions.clear()
        for records in grouped.values():
            newest = max(records, key=lambda row: row["last_record"])
            association = max(records, key=lambda row: row["last_used"])
            merged = {
                **newest,
                "last_used": association["last_used"],
                "evidence": association["evidence"],
            }
            for field in ("last_workspace_use", "last_reference"):
                merged[field] = max(row[field] for row in records)
            merged["association"] = (
                "workspace" if merged["last_workspace_use"] else "reference_only"
            )
            sessions.append(merged)
        sessions.sort(key=lambda row: (row["loaded"] != "loaded", -row["last_used"]))
    return matches, warnings


def classify(
    facts: dict[str, Any], *, main: str, current: str, cutoff: float
) -> tuple[str, str]:
    if facts["path"] == main:
        return "main", "Keep the main worktree"
    if facts["path"] == current:
        return "current", "Keep the invoking worktree"
    if facts.get("locked"):
        return "locked", "Retain the locked worktree"
    if facts.get("missing"):
        return "missing", "Directory missing; inspect its Git registration"
    if facts.get("error"):
        return "unknown", facts["error"]
    if any(
        session["loaded"] == "loaded" and session["association"] == "workspace"
        for session in facts["sessions"]
    ):
        return (
            "active",
            "A loaded session has workspace evidence; inspect context to confirm current ownership",
        )
    if (
        max(
            [facts["last_edit"], facts["last_content_update"], facts["last_checkout"]]
            + [session["last_workspace_use"] for session in facts["sessions"]]
        )
        >= cutoff
    ):
        return (
            "recent",
            "Recent content/workspace activity; inspect remaining diffs and completion before deciding",
        )
    if facts["ancestor"] and not facts["changes"] and not facts["ignored"]:
        return "merged", "Clean and HEAD is an ancestor of main; cleanup candidate"
    if (
        not facts["unique_patches"]
        and not facts["unlanded"]
        and not facts["staged_unlanded"]
    ):
        return (
            "landed",
            "Content/patches appear landed; inspect index and local files before cleanup",
        )
    return "unmerged", "Unique commits or local changes remain; retain and investigate"


def process_references(
    paths: list[str], proc_root: Path = Path("/proc")
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Inspect same-user cwd/fd references; never infer Codex writer-lock state."""
    matches: dict[str, list[dict[str, Any]]] = {path: [] for path in paths}
    if not proc_root.is_dir():
        return matches, ["Process references unavailable: /proc is not available"]
    unreadable = 0
    for process in proc_root.iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            cwd = os.readlink(process / "cwd")
            links = [("cwd", cwd)]
            fd_scan_complete = True
            try:
                for fd in (process / "fd").iterdir():
                    try:
                        links.append(("fd", os.readlink(fd)))
                    except FileNotFoundError:
                        pass  # File descriptors can close during the scan.
            except PermissionError:
                unreadable += 1
                fd_scan_complete = False
            for path in paths:
                references = [
                    {"kind": kind, "path": target}
                    for kind, target in links
                    if target == path or target.startswith(path + "/")
                ]
                if not references:
                    continue
                name = (process / "comm").read_text().strip()
                fields = (process / "stat").read_text().rpartition(") ")[2].split()
                children = (
                    (process / "task" / process.name / "children").read_text().split()
                )
                idle = (
                    name in {"sh", "bash", "zsh", "fish"}
                    and fields[0] == "S"
                    and not children
                    and fd_scan_complete
                    and all(r["kind"] == "cwd" for r in references)
                )
                matches[path].append(
                    {
                        "pid": int(process.name),
                        "name": name,
                        "state": fields[0],
                        "children": children,
                        "references": references,
                        "fd_scan_complete": fd_scan_complete,
                        "idle_shell_candidate": idle,
                    }
                )
        except (FileNotFoundError, ProcessLookupError):
            pass  # Processes can exit during the scan.
        except (OSError, IndexError):
            unreadable += 1
    warnings = (
        [f"Process scan incomplete for {unreadable} same-user process resources"]
        if unreadable
        else []
    )
    return matches, warnings


def remote_facts(
    workspace: Path, rows: list[dict[str, Any]], live: bool
) -> dict[str, dict[str, Any]]:
    remotes = git(workspace, "remote").splitlines()
    live_heads: dict[str, dict[str, str]] = {}
    failures: dict[str, str] = {}
    if live:
        for remote in remotes:
            try:
                result = subprocess.run(
                    [
                        "git",
                        "--no-optional-locks",
                        "-C",
                        str(workspace),
                        "ls-remote",
                        "--heads",
                        remote,
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    env={
                        **os.environ,
                        "GIT_TERMINAL_PROMPT": "0",
                        "SSH_ASKPASS_REQUIRE": "never",
                    },
                )
                if result.returncode:
                    failures[remote] = (
                        result.stderr.strip()[:1000] or "Remote query failed"
                    )
                else:
                    live_heads[remote] = {
                        ref: oid
                        for oid, ref in (
                            line.split("\t", 1) for line in result.stdout.splitlines()
                        )
                    }
            except (OSError, subprocess.TimeoutExpired) as exc:
                failures[remote] = str(exc)
    result_rows = {}
    for row in rows:
        branch = row.get("branch")
        if not branch:
            result_rows[row["path"]] = {"status": "detached"}
            continue
        raw = git(
            workspace,
            "for-each-ref",
            "--format=%(upstream)%00%(upstream:remotename)%00%(upstream:remoteref)",
            "refs/heads/" + branch,
        ).strip()
        upstream, remote, remote_ref = raw.split("\0") if raw else ("", "", "")
        cached = (
            git(workspace, "rev-parse", "--verify", upstream, allowed=(0, 128)).strip()
            if upstream
            else ""
        )
        same_named = "refs/heads/" + branch
        info: dict[str, Any] = {
            "upstream": upstream or None,
            "cached_sha": cached or None,
            "cached_matches_head": bool(cached) and cached == row["HEAD"],
            "status": "not_checked" if live else "cached_only",
        }
        if cached:
            ahead, behind = git(
                workspace,
                "rev-list",
                "--left-right",
                "--count",
                f"{row['HEAD']}...{cached}",
            ).split()
            info.update(cached_ahead=int(ahead), cached_behind=int(behind))
        if remote == ".":
            info["status"] = "local_upstream"
        elif live:
            checks = (
                [(remote, remote_ref)]
                if remote
                else [(name, same_named) for name in remotes]
            )
            info["live_branches"] = [
                {
                    "remote": name,
                    "ref": ref,
                    "sha": live_heads[name].get(ref),
                    "matches_head": live_heads[name].get(ref) == row["HEAD"],
                }
                for name, ref in checks
                if name in live_heads
            ]
            info["errors"] = {
                name: failures[name] for name, _ in checks if name in failures
            }
            if any(b["matches_head"] for b in info["live_branches"]):
                info["status"] = "verified_match"
            elif info["errors"]:
                info["status"] = "unavailable"
            elif any(b["sha"] for b in info["live_branches"]):
                info["status"] = "verified_different"
            else:
                info["status"] = "no_matching_branch" if remotes else "no_remotes"
        result_rows[row["path"]] = info
    return result_rows


def build_report(
    workspace: Path,
    home: Path,
    hours: float,
    exclude: set[str],
    *,
    live_remotes: bool = False,
) -> dict[str, Any]:
    rows = list_worktrees(workspace)
    main = rows[0]
    current = str(
        Path(git(workspace, "rev-parse", "--show-toplevel").strip()).resolve()
    )
    sessions, warnings = scan_sessions(home, [row["path"] for row in rows], exclude)
    processes, process_warnings = process_references([row["path"] for row in rows])
    warnings.extend(process_warnings)
    remotes = remote_facts(workspace, rows, live_remotes)
    facts = []
    cutoff = time.time() - hours * 3600
    for row in rows:
        fact = git_facts(row, main)
        fact["sessions"] = sessions[row["path"]]
        fact["processes"] = processes[row["path"]]
        fact["remote"] = remotes[row["path"]]
        fact["category"], fact["recommendation"] = classify(
            fact, main=main["path"], current=current, cutoff=cutoff
        )
        facts.append(fact)
    if (
        git(workspace, "rev-parse", main["HEAD"]).strip()
        != git(Path(main["path"]), "rev-parse", "HEAD").strip()
    ):
        warnings.append("Main HEAD changed during inspection; refresh before acting")
    if list_worktrees(workspace) != rows:
        warnings.append(
            "Worktree registrations or branch tips changed during inspection; refresh before acting"
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "comparison_head": main["HEAD"],
        "main": main["path"],
        "current": current,
        "codex_home": str(home),
        "hours": hours,
        "excluded_sessions": sorted(exclude),
        "warnings": warnings,
        "worktrees": facts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))),
    )
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--live-remotes",
        action="store_true",
        help="Query remote branch tips without fetching or updating refs",
    )
    parser.add_argument("--context", type=Path)
    parser.add_argument("--exclude-sid", action="append", default=[])
    args = parser.parse_args()
    if not 0 <= args.hours < float("inf"):
        parser.error("--hours must be a finite non-negative number")
    exclude = set(args.exclude_sid)
    if sid := os.environ.get("CODEX_THREAD_ID"):
        exclude.add(sid)
    try:
        report = build_report(
            args.workspace.resolve(),
            args.codex_home.expanduser().resolve(),
            args.hours,
            exclude,
            live_remotes=args.live_remotes,
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Cannot inspect worktrees: {exc}\n")
    if args.context:
        target = str(args.context.resolve())
        row = next((row for row in report["worktrees"] if row["path"] == target), None)
        if row is None:
            parser.error(f"Not a worktree of this repository: {target}")
        print(
            json.dumps(
                {
                    "main": report["main"],
                    "warnings": report["warnings"],
                    "worktree": row,
                },
                indent=2,
            )
        )
    elif args.json:
        for row in report["worktrees"]:
            for session in row["sessions"]:
                session.pop("messages", None)
        print(json.dumps(report, indent=2))
    else:
        print(f"Main worktree: {report['main']}\nCodex home: {report['codex_home']}")
        for warning in report["warnings"]:
            print(f"Warning: {warning}")
        for row in report["worktrees"]:
            print(
                f"\n{row['category']:9} {row['path']} ({row.get('branch') or 'detached'})"
            )
            print(f"  {row['recommendation']}")
            print(
                f"  ahead={row.get('ahead', '?')} behind={row.get('behind', '?')} changes={len(row['changes'])} ignored={len(row['ignored'])}"
            )
            for label, key in (
                ("Content update", "last_content_update"),
                ("Checkout/reflog", "last_checkout"),
            ):
                when = row.get(key, 0)
                print(
                    f"  {label}: {datetime.fromtimestamp(when).astimezone().isoformat() if when else 'unknown'}"
                )
            print(
                f"  Remaining vs committed main: files={len(row.get('unlanded', []))} staged={len(row.get('staged_unlanded', []))}; remote={row['remote']['status']}"
            )
            print(
                f"  Process references: {len(row['processes'])} ({sum(p['idle_shell_candidate'] for p in row['processes'])} idle-shell candidates)"
            )
            for session in row["sessions"][:5]:
                print(
                    f"  Codex {session['id']} [{session['loaded']}; {session['last_event']}; {session['association']}] {session['title'].splitlines()[0] if session['title'] else '(untitled)'}"
                )
            if not row["sessions"]:
                print("  No local Codex session evidence (not proof of abandonment)")


if __name__ == "__main__":
    main()
