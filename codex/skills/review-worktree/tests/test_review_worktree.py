"""Behavioral checks using temporary repositories and synthetic Codex sessions."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from review_worktree import (
    build_report,
    git,
    loaded_state,
    process_references,
    remote_facts,
    scan_sessions,
    status_paths,
)


class ReviewWorktreeTest(unittest.TestCase):
    temp: tempfile.TemporaryDirectory[str]
    root: Path
    repo: Path
    home: Path

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="review-worktree-test-")
        self.root = Path(self.temp.name)
        self.repo = self.root / "main"
        self.home = self.root / "codex"
        self.repo.mkdir()
        (self.home / "sessions").mkdir(parents=True)
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Skill Test")
        git(self.repo, "config", "user.email", "skill-test@example.invalid")
        (self.repo / "file").write_text("base\n")
        (self.repo / ".gitignore").write_text("ignored/\n")
        git(self.repo, "add", "file", ".gitignore")
        git(self.repo, "commit", "-m", "base")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def worktree(self, name: str) -> Path:
        path = self.root / name
        git(self.repo, "worktree", "add", "-b", name.replace(" ", "-"), str(path))
        return path

    def report_row(self, path: Path, hours: float = 0) -> dict[str, Any]:
        report = build_report(self.repo, self.home, hours, set())
        return next(row for row in report["worktrees"] if row["path"] == str(path))

    def rollout(self, sid: str, events: list[dict[str, Any]]) -> None:
        path = self.home / "sessions" / f"{sid}.jsonl"
        events = [
            {"type": "session_meta", "payload": {"id": sid, "cwd": str(self.repo)}}
        ] + events
        with path.open("w") as handle:
            for event in events:
                event["timestamp"] = datetime.now(timezone.utc).isoformat()
                handle.write(json.dumps(event) + "\n")

    def test_clean_ancestor_and_unique_commit(self) -> None:
        clean = self.worktree("clean with spaces")
        unique = self.worktree("unique")
        (unique / "file").write_text("unique\n")
        git(unique, "commit", "-am", "unique commit")
        self.assertEqual(self.report_row(clean)["category"], "merged")
        self.assertEqual(self.report_row(unique)["category"], "unmerged")

    def test_local_and_ignored_files_are_not_clean_candidates(self) -> None:
        work = self.worktree("local")
        (work / "untracked").write_text("valuable work\n")
        self.assertEqual(self.report_row(work)["category"], "unmerged")
        (work / "untracked").unlink()
        (work / "ignored").mkdir()
        (work / "ignored" / "data").write_text("keep\n")
        self.assertEqual(self.report_row(work)["category"], "landed")

    def test_distinct_staged_content_is_retained(self) -> None:
        work = self.worktree("staged")
        (work / "file").write_text("staged work\n")
        git(work, "add", "file")
        (work / "file").write_text("base\n")
        before = git(work, "diff", "--cached")
        row = self.report_row(work)
        self.assertEqual(row["category"], "unmerged")
        self.assertEqual(row["staged_unlanded"], ["file"])
        self.assertEqual(git(work, "diff", "--cached"), before)

    def test_rename_preserves_deletion_evidence(self) -> None:
        self.assertEqual(status_paths("R  new\0old\0"), [("R ", "new"), ("D ", "old")])

    def test_mode_changes_are_unlanded(self) -> None:
        work = self.worktree("mode")
        (work / "file").chmod(0o755)
        self.assertEqual(self.report_row(work)["category"], "unmerged")

    def test_codex_evidence_ignores_quoted_paths_and_reviewer_output(self) -> None:
        work = self.worktree("owned")
        quoted = self.worktree("quoted")
        self.rollout(
            "worker",
            [
                {"type": "turn_context", "payload": {"cwd": str(work)}},
                {
                    "type": "event_msg",
                    "payload": {"type": "task_started", "turn_id": "one"},
                },
                {
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": str(quoted)},
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "output": str(quoted),
                    },
                },
            ],
        )
        self.rollout(
            "reviewer",
            [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "input": f"python review_worktree.py --context {quoted}",
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": str(quoted)},
                },
            ],
        )
        matches, warnings = scan_sessions(self.home, [str(work), str(quoted)], set())
        self.assertFalse(warnings)
        self.assertEqual([s["id"] for s in matches[str(work)]], ["worker"])
        self.assertEqual(matches[str(quoted)], [])
        self.assertEqual(self.report_row(work, hours=24)["category"], "recent")
        self.assertEqual(
            scan_sessions(self.home, [str(work)], {"worker"})[0][str(work)], []
        )

    def test_tools_from_a_sibling_session_associate_exact_paths(self) -> None:
        work = self.worktree("work")
        sibling = self.worktree("work-extra")
        self.rollout(
            "worker",
            [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "arguments": json.dumps({"cmd": f"git -C {sibling} diff"}),
                    },
                }
            ],
        )
        matches, _ = scan_sessions(self.home, [str(work), str(sibling)], set())
        self.assertEqual(matches[str(work)], [])
        self.assertEqual(matches[str(sibling)][0]["id"], "worker")
        self.assertEqual(matches[str(sibling)][0]["association"], "reference_only")

    def test_lock_is_loaded_not_automatically_busy(self) -> None:
        locks = self.home / "thread-writer-locks"
        locks.mkdir()
        lock = locks / "session.lock"
        lock.touch()
        self.assertEqual(loaded_state(self.home, "session"), "not loaded")
        with lock.open("rb") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(loaded_state(self.home, "session"), "loaded")
        self.assertEqual(loaded_state(self.home, "missing"), "unknown")

    def test_current_and_locked_worktrees_are_retained(self) -> None:
        work = self.worktree("current")
        report = build_report(work, self.home, 0, set())
        self.assertEqual(
            next(row for row in report["worktrees"] if row["path"] == str(work))[
                "category"
            ],
            "current",
        )
        git(self.repo, "worktree", "lock", str(work))
        self.assertEqual(self.report_row(work)["category"], "locked")

    def test_recent_dirty_work_and_missing_session_data(self) -> None:
        work = self.worktree("recent")
        (work / "new").write_text("ongoing\n")
        self.assertEqual(self.report_row(work, hours=24)["category"], "recent")
        report = build_report(self.repo, self.home, 24, set())
        self.assertTrue(report["warnings"])
        before = git(work, "status", "--porcelain=v1")
        index = Path(git(work, "rev-parse", "--git-path", "index").strip())
        stamp = index.stat().st_mtime_ns
        build_report(self.repo, self.home, 24, set())
        self.assertEqual(index.stat().st_mtime_ns, stamp)
        self.assertEqual(git(work, "status", "--porcelain=v1"), before)

    def test_working_copy_match_is_not_committed_in_main(self) -> None:
        work = self.worktree("uncommitted-main")
        (work / "file").write_text("not committed\n")
        (self.repo / "file").write_text("not committed\n")
        row = self.report_row(work)
        self.assertEqual(row["category"], "unmerged")
        self.assertTrue(row["content_comparison"][0]["matches_main_worktree"])
        self.assertFalse(row["content_comparison"][0]["matches_main_head"])

    def test_recent_reference_from_loaded_reviewer_is_not_ownership(self) -> None:
        work = self.worktree("inspected")
        self.rollout(
            "reviewer",
            [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "arguments": json.dumps({"cmd": f"git -C {work} diff"}),
                    },
                }
            ],
        )
        locks = self.home / "thread-writer-locks"
        locks.mkdir()
        with (locks / "reviewer.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            row = self.report_row(work)
        self.assertEqual(row["sessions"][0]["loaded"], "loaded")
        self.assertEqual(row["sessions"][0]["association"], "reference_only")
        self.assertEqual(row["category"], "merged")

    def test_explicit_execution_cwd_is_workspace_evidence(self) -> None:
        work = self.worktree("execution")
        self.rollout(
            "worker",
            [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "arguments": json.dumps(
                            {"cmd": "pytest", "workdir": str(work)}
                        ),
                    },
                }
            ],
        )
        matches, _ = scan_sessions(self.home, [str(work)], set())
        self.assertEqual(matches[str(work)][0]["association"], "workspace")
        self.assertGreater(matches[str(work)][0]["last_workspace_use"], 0)

    def test_duplicate_rollouts_do_not_duplicate_threads(self) -> None:
        work = self.worktree("duplicate")
        self.rollout(
            "worker", [{"type": "turn_context", "payload": {"cwd": str(work)}}]
        )
        original = self.home / "sessions" / "worker.jsonl"
        copy = self.home / "archived_sessions" / "copy.jsonl"
        copy.parent.mkdir()
        copy.write_bytes(original.read_bytes())
        matches, _ = scan_sessions(self.home, [str(work)], set())
        self.assertEqual(len(matches[str(work)]), 1)

    def test_content_update_excludes_inspection_and_index_refresh(self) -> None:
        work = self.worktree("timestamps")
        (work / "file").write_text("changed\n")
        old = 1_000_000_000
        os.utime(work / "file", (old, old))
        self.rollout(
            "reviewer",
            [
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "arguments": json.dumps({"cmd": f"git -C {work} diff"}),
                    },
                }
            ],
        )
        row = self.report_row(work)
        self.assertEqual(row["last_file_edit"], old)
        self.assertEqual(row["last_content_update"], row["last_commit"])
        self.assertGreater(
            row["sessions"][0]["last_reference"], row["last_content_update"]
        )

    def test_live_remote_differs_while_cached_tip_still_matches(self) -> None:
        remote = self.root / "remote.git"
        git(self.repo, "init", "--bare", str(remote))
        git(self.repo, "remote", "add", "origin", str(remote))
        git(self.repo, "push", "-u", "origin", "main")
        writer = self.root / "writer"
        git(self.repo, "clone", "-b", "main", str(remote), str(writer))
        git(writer, "config", "user.name", "Other Writer")
        git(writer, "config", "user.email", "other@example.invalid")
        (writer / "file").write_text("remote update\n")
        git(writer, "commit", "-am", "advance remote")
        git(writer, "push", "origin", "main")
        row = {
            "path": str(self.repo),
            "branch": "main",
            "HEAD": git(self.repo, "rev-parse", "HEAD").strip(),
        }
        facts = remote_facts(self.repo, [row], True)[str(self.repo)]
        self.assertTrue(facts["cached_matches_head"])
        self.assertEqual(facts["status"], "verified_different")
        self.assertEqual(
            git(self.repo, "rev-parse", "origin/main").strip(), row["HEAD"]
        )
        remote.rename(self.root / "unavailable.git")
        failed = remote_facts(self.repo, [row], True)[str(self.repo)]
        self.assertEqual(failed["status"], "unavailable")
        self.assertTrue(failed["cached_matches_head"])

    def test_shell_with_child_is_not_idle_shell_candidate(self) -> None:
        work = self.worktree("process")
        proc = self.root / "proc"
        shell = proc / "123"
        (shell / "fd").mkdir(parents=True)
        (shell / "task" / "123").mkdir(parents=True)
        (shell / "cwd").symlink_to(work)
        (shell / "comm").write_text("zsh\n")
        (shell / "stat").write_text("123 (zsh) S 1 123 123 0 123\n")
        children = shell / "task" / "123" / "children"
        children.write_text("")
        references, warnings = process_references([str(work)], proc)
        self.assertFalse(warnings)
        self.assertTrue(references[str(work)][0]["idle_shell_candidate"])
        children.write_text("456")
        references, _ = process_references([str(work)], proc)
        self.assertFalse(references[str(work)][0]["idle_shell_candidate"])
        children.write_text("")
        original_iterdir = Path.iterdir

        def incomplete_iterdir(path: Path) -> Any:
            if path == shell / "fd":
                raise PermissionError("fd inspection denied")
            return original_iterdir(path)

        with patch.object(Path, "iterdir", incomplete_iterdir):
            references, warnings = process_references([str(work)], proc)
        self.assertTrue(warnings)
        self.assertFalse(references[str(work)][0]["idle_shell_candidate"])
        self.assertFalse(references[str(work)][0]["fd_scan_complete"])


if __name__ == "__main__":
    unittest.main()
