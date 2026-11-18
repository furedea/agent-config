"""Stop-time model rules: commits already on the remote default branch are not reviewed."""

import subprocess
from pathlib import Path

import pytest
import session_store
from tests.hooks.model_rules_fakes import Tools
from tests.hooks.model_rules_support import commit_file, edit, install_fakes, register_session, stop
from tests.runtime import StubWriter


@pytest.fixture(autouse=True)
def tools(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    return install_fakes(executable, tmp_path, monkeypatch)


@pytest.fixture
def record(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> session_store.SessionRecord:
    registered = register_session(git_project, tmp_path, monkeypatch)
    edit(registered, "after\n")
    return registered


def _publish_default_branch(record: session_store.SessionRecord, commit: str) -> None:
    root = record.root
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", commit], cwd=root, check=True)
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"], cwd=root, check=True
    )


def _head(record: session_store.SessionRecord) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=record.root, text=True).strip()


def test_commits_already_on_the_remote_default_branch_are_not_reviewed(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    commit_file(record, "merged.txt")
    merged = _head(record)
    _publish_default_branch(record, merged)
    commit_file(record, "mine.txt")

    stop(record)

    committed, _ = tools.calls("op")
    assert committed["argv"][committed["argv"].index("--base") + 1] == merged
    assert "merged.txt" not in committed["argv"]
    assert committed["argv"][-1] == "mine.txt"


def test_a_default_branch_that_does_not_lead_to_the_starting_commit_leaves_the_base_at_the_starting_commit(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    commit_file(record, "mine.txt")
    unrelated = subprocess.check_output(
        ["git", "commit-tree", "-m", "unrelated", "HEAD^{tree}"], cwd=record.root, text=True
    ).strip()
    _publish_default_branch(record, unrelated)

    stop(record)

    committed, _ = tools.calls("op")
    assert committed["argv"][committed["argv"].index("--base") + 1] == record.head
    assert committed["argv"][-1] == "mine.txt"
