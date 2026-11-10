"""A session records the commit HEAD named when it registered, so later review can include commits made since."""

import subprocess
import sys
from pathlib import Path

import pytest
from tests.runtime import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import session_store


@pytest.fixture
def state(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path.parent / f"{tmp_path.name}-state"))
    return git_project


def commit_id(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_registration_records_the_commit_head_named(state: Path) -> None:
    record = session_store.register(state, "claude", "head-test")

    assert record.head == commit_id(state)


def test_the_recorded_head_does_not_follow_commits_made_after_registration(state: Path) -> None:
    record = session_store.register(state, "claude", "head-test")
    registered = commit_id(state)
    subprocess.run(["git", "commit", "--quiet", "--allow-empty", "-m", "later"], cwd=state, check=True)

    assert commit_id(state) != registered
    assert session_store.load(record.directory).head == registered


def test_a_repository_without_a_commit_has_no_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path.parent / f"{tmp_path.name}-state"))
    root = tmp_path / "empty"
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)

    assert session_store.register(root, "claude", "head-test").head is None


def test_a_record_written_before_heads_were_recorded_has_no_head(state: Path) -> None:
    record = session_store.register(state, "claude", "head-test")
    baseline = record.directory / "baseline.json"
    stored = session_store.read_json(baseline)
    del stored["head"]
    session_store.atomic_json(baseline, stored)

    assert session_store.load(record.directory).head is None


def test_a_head_that_is_not_a_commit_id_is_ignored(state: Path) -> None:
    record = session_store.register(state, "claude", "head-test")
    baseline = record.directory / "baseline.json"
    session_store.atomic_json(baseline, {**session_store.read_json(baseline), "head": "--output=/tmp/x"})

    assert session_store.load(record.directory).head is None
