"""Audit rows keep only guard and approval decisions, bounded, without event bodies."""

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.runtime import load_script_module

audit = load_script_module("agents/hooks/audit_log.py", "audit_log")


def test_denial_does_not_retain_reason_or_command() -> None:
    entry = audit.record(
        {
            "tool_name": "Bash",
            "reason": "requires approval: token=secret-value",
            "tool_input": {"command": "curl https://user:password@example.invalid"},
            "session_id": "session-one",
        },
    )
    assert entry["status"] == "denied"
    assert entry["event"] == "PermissionDenied"
    assert entry["session"] != "session-one"
    assert entry["targets"] == []
    assert "duration_ms" not in entry
    assert "reason" not in entry
    assert "input" not in entry
    assert "secret-value" not in str(entry)
    assert "password" not in str(entry)


def test_timestamp_is_utc_when_appended(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    audit.append_record(audit.record({"tool_name": "Bash", "tool_input": {"command": "git status"}}))
    rows = [
        json.loads(line)
        for path in (tmp_path / "state/agent-harness/audit").glob("*/*/*.jsonl")
        for line in path.read_text().splitlines()
    ]
    timestamp = datetime.fromisoformat(rows[0]["ts"])
    assert timestamp.tzinfo == UTC
    assert timestamp.utcoffset() == timedelta(0)


def test_escalation_records_the_governed_prefix_without_the_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    command = "git commit -m 'token=secret-value'"
    audit.escalated(
        audit.Refusal(
            "Bash",
            "guard_allowed_commands.sh",
            "session-one",
            payload={"tool_name": "Bash", "tool_input": {"command": command}, "session_id": "session-one"},
            detail="git commit",
        )
    )
    [row] = [
        json.loads(line)
        for path in (tmp_path / "state/agent-harness/audit").glob("*/*/*.jsonl")
        for line in path.read_text().splitlines()
    ]
    assert row["event"] == "Escalated"
    assert row["status"] == "asked"
    assert row["rule"] == "guard_allowed_commands.sh"
    assert row["detail"] == "git_commit"
    assert "secret-value" not in json.dumps(row)


def test_rotation_keeps_each_audit_file_under_the_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worktree = tmp_path / "worktree"
    state = tmp_path / "state"
    worktree.mkdir()
    monkeypatch.chdir(worktree)
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setattr(audit, "LOG_LIMIT_BYTES", 600)
    monkeypatch.setattr(audit, "CLEANUP_INTERVAL_SECONDS", 0)
    for _ in range(8):
        audit.append_record(
            audit.record({"tool_name": "Bash", "session_id": "session", "tool_input": {"command": "true"}}),
            cwd=worktree,
        )
    paths = list((state / "agent-harness/audit").glob("*/*/*.jsonl"))
    assert len(paths) > 1
    assert all(path.stat().st_size <= 600 for path in paths)
    assert all(
        json.loads(line)["event"] == "PermissionDenied" for path in paths for line in path.read_text().splitlines()
    )


def test_retention_and_total_size_limits_are_applied_without_corrupting_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = tmp_path / "worktree"
    state = tmp_path / "state"
    worktree.mkdir()
    monkeypatch.chdir(worktree)
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setattr(audit, "TOTAL_LOG_LIMIT_BYTES", 900)
    monkeypatch.setattr(audit, "CLEANUP_INTERVAL_SECONDS", 0)
    for _ in range(12):
        audit.append_record(
            audit.record({"tool_name": "Bash", "session_id": "session", "tool_input": {"command": "true"}}),
            cwd=worktree,
        )
    paths = list((state / "agent-harness/audit").glob("*/*/*.jsonl"))
    assert sum(path.stat().st_size for path in paths) <= 900
    oldest = paths[0]
    os.utime(oldest, (1, 1))
    audit.prune(now=time.time() + audit.RETENTION_SECONDS + 2)
    assert not oldest.exists()
    assert all(json.loads(line) for path in paths if path.exists() for line in path.read_text().splitlines())


def test_a_refusal_keeps_only_a_relative_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    worktree = tmp_path / "worktree"
    audit.blocked(
        audit.Refusal(
            "Write",
            "guard_file.py",
            "session-one",
            payload={"cwd": str(worktree), "tool_input": {"content": "private body"}},
            targets=(str(worktree / "src/file.py"), "https://user:password@example.invalid/private"),
        )
    )
    [row] = [
        json.loads(line)
        for path in (tmp_path / "state/agent-harness/audit").glob("*/*/*.jsonl")
        for line in path.read_text().splitlines()
    ]
    assert row["targets"] == ["src/file.py", "external"]
    assert "private body" not in json.dumps(row)
    assert "password" not in json.dumps(row)


@pytest.mark.parametrize("name", ["transcript_counts", "_targets", "_duration", "_compaction_record"])
def test_per_call_and_compaction_observation_code_is_gone(name: str) -> None:
    assert not hasattr(audit, name)
