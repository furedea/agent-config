"""Stop model rules judge the commits the session made, not the ones it fast-forwarded or pulled in."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import Tools
from tests.hooks.model_rules_support import edit, install_fakes, register_session, stop
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_files
import session_store


def git(root: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True, env={**os.environ, **(env or {})}
    )
    return result.stdout.strip()


def commit(root: Path, name: str, text: str = "x\n") -> None:
    (root / name).write_text(text)
    git(root, "add", name)
    git(root, "commit", "--quiet", "-m", f"add {name}")


def others_work(root: Path, *names: str) -> None:
    """Commits another session made in its own clone, fetched here as the branch `others` but not merged."""
    clone = root.with_name(f"{root.name}-other")
    git(root, "clone", "--quiet", str(root), str(clone))
    git(clone, "config", "user.email", "other@example.invalid")
    git(clone, "config", "user.name", "Other")
    for name in names:
        commit(clone, name)
    git(root, "fetch", "--quiet", str(clone), "main:others")


def own_paths(root: Path, base: str, registered_at: float = 0.0) -> tuple[str, ...]:
    return model_rules_files.own_committed_paths(root, base, registered_at)


@pytest.fixture
def base(git_project: Path) -> str:
    return git(git_project, "rev-parse", "HEAD")


def test_a_fast_forward_brings_in_files_that_are_not_the_sessions(git_project: Path, base: str) -> None:
    others_work(git_project, "theirs.py", "also_theirs.py")

    git(git_project, "merge", "--quiet", "--ff-only", "others")

    assert own_paths(git_project, base) == ()


def test_a_pull_that_fast_forwards_brings_in_files_that_are_not_the_sessions(git_project: Path, base: str) -> None:
    others_work(git_project, "theirs.py")
    git(git_project, "remote", "add", "upstream", str(git_project))
    git(git_project, "fetch", "--quiet", "upstream", "others")

    git(git_project, "pull", "--quiet", "--ff-only", "upstream", "others")

    assert own_paths(git_project, base) == ()


def test_own_commits_count_beside_commits_fast_forwarded_in(git_project: Path, base: str) -> None:
    others_work(git_project, "theirs.py")
    commit(git_project, "mine.py")
    git(git_project, "rebase", "--quiet", "others")

    assert own_paths(git_project, base) == ("mine.py",)


def test_an_amended_commit_counts_once_under_its_new_identity(git_project: Path, base: str) -> None:
    commit(git_project, "mine.py")
    (git_project / "more.py").write_text("x\n")
    git(git_project, "add", "more.py")
    git(git_project, "commit", "--quiet", "--amend", "--no-edit")

    assert own_paths(git_project, base) == ("mine.py", "more.py")


def test_amending_a_commit_that_predates_the_session_counts_only_what_the_amend_changed(git_project: Path) -> None:
    commit(git_project, "old.txt")
    base = git(git_project, "rev-parse", "HEAD")
    (git_project / "new.txt").write_text("x\n")
    git(git_project, "add", "new.txt")

    git(git_project, "commit", "--quiet", "--amend", "--no-edit")

    assert own_paths(git_project, base) == ("new.txt",)


def test_a_commit_made_on_a_side_branch_and_fast_forwarded_still_counts(git_project: Path, base: str) -> None:
    git(git_project, "switch", "--quiet", "-c", "side")
    commit(git_project, "mine.py")
    git(git_project, "switch", "--quiet", "main")

    git(git_project, "merge", "--quiet", "--ff-only", "side")

    assert own_paths(git_project, base) == ("mine.py",)


def test_a_merge_commit_is_not_counted_for_the_files_it_merged_in(git_project: Path, base: str) -> None:
    others_work(git_project, "theirs.py")
    commit(git_project, "mine.py")

    git(git_project, "merge", "--quiet", "--no-ff", "-m", "merge", "others")

    assert own_paths(git_project, base) == ("mine.py",)


def test_a_pull_that_rebases_keeps_the_sessions_own_commits(git_project: Path, base: str) -> None:
    others_work(git_project, "theirs.txt")
    commit(git_project, "mine.txt")
    git(git_project, "remote", "add", "upstream", str(git_project))
    git(git_project, "fetch", "--quiet", "upstream", "others")

    git(git_project, "pull", "--quiet", "--rebase", "upstream", "others")

    assert own_paths(git_project, base) == ("mine.txt",)


def test_a_cherry_pick_is_the_sessions_commit(git_project: Path, base: str) -> None:
    others_work(git_project, "theirs.txt")

    git(git_project, "cherry-pick", "others")

    assert own_paths(git_project, base) == ("theirs.txt",)


def test_a_revert_is_the_sessions_commit(git_project: Path) -> None:
    commit(git_project, "f.txt", "a\n")
    commit(git_project, "f.txt", "b\n")
    base = git(git_project, "rev-parse", "HEAD")

    git(git_project, "revert", "--no-edit", "HEAD")

    assert own_paths(git_project, base) == ("f.txt",)


def test_a_commit_made_before_the_session_and_fast_forwarded_in_is_not_the_sessions(
    git_project: Path, base: str
) -> None:
    long_ago = {"GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z"}
    git(git_project, "switch", "--quiet", "-c", "side")
    (git_project / "earlier.txt").write_text("x\n")
    git(git_project, "add", "earlier.txt")
    git(git_project, "commit", "--quiet", "-m", "earlier", env=long_ago)
    git(git_project, "switch", "--quiet", "main")

    git(git_project, "merge", "--quiet", "--ff-only", "side")

    assert own_paths(git_project, base, registered_at=time.time() - 60) == ()


def test_a_failing_git_is_reported_as_a_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot be listed"):
        own_paths(tmp_path, "HEAD")


def test_the_stop_hook_does_not_advise_on_files_it_fast_forwarded_in(
    git_project: Path, tmp_path: Path, executable: StubWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools: Tools = install_fakes(executable, tmp_path, monkeypatch)
    record: session_store.SessionRecord = register_session(git_project, tmp_path, monkeypatch)
    others_work(git_project, "theirs.txt")
    git(git_project, "merge", "--quiet", "--ff-only", "others")
    edit(record, "after\n")

    stop(record)

    assert tools.calls("op")
    for call in tools.calls("op"):
        assert "theirs.txt" not in call["argv"]
