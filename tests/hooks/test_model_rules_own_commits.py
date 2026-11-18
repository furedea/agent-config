"""Stop model rules judge the commits the session made, not the ones it fast-forwarded or pulled in."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import Tools
from tests.hooks.model_rules_support import edit, install_fakes, register_session, stop
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_files
import model_rules_gate
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


def own_paths(root: Path, base: str, registered_entries: int | None = 0) -> tuple[str, ...]:
    return model_rules_files.own_committed_paths(root, base, registered_entries)


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


def test_a_cherry_pick_finished_by_hand_after_a_conflict_is_the_sessions_commit(git_project: Path) -> None:
    commit(git_project, "f.txt", "base\n")
    git(git_project, "switch", "--quiet", "-c", "side")
    commit(git_project, "f.txt", "side\n")
    git(git_project, "switch", "--quiet", "main")
    commit(git_project, "f.txt", "main\n")
    base = git(git_project, "rev-parse", "HEAD")
    registered_entries = len(git(git_project, "reflog", "show", "--format=%H", "HEAD").splitlines())
    subprocess.run(["git", "cherry-pick", "side"], check=False, cwd=git_project, capture_output=True)
    (git_project / "f.txt").write_text("resolved\n")
    git(git_project, "add", "f.txt")

    git(git_project, "commit", "--quiet", "-m", "resolved")

    assert own_paths(git_project, base, registered_entries) == ("f.txt",)


def test_a_revert_is_the_sessions_commit(git_project: Path) -> None:
    commit(git_project, "f.txt", "a\n")
    commit(git_project, "f.txt", "b\n")
    base = git(git_project, "rev-parse", "HEAD")

    git(git_project, "revert", "--no-edit", "HEAD")

    assert own_paths(git_project, base) == ("f.txt",)


def test_a_commit_made_before_the_session_and_fast_forwarded_in_is_not_the_sessions(
    git_project: Path, base: str
) -> None:
    git(git_project, "switch", "--quiet", "-c", "side")
    commit(git_project, "earlier.txt")
    git(git_project, "switch", "--quiet", "main")
    registered_entries = len(git(git_project, "reflog", "show", "--format=%H", "HEAD").splitlines())

    git(git_project, "merge", "--quiet", "--ff-only", "side")

    assert own_paths(git_project, base, registered_entries) == ()


def test_amending_a_fast_forwarded_tip_counts_only_what_the_amend_added(git_project: Path, base: str) -> None:
    others_work(git_project, "theirs.txt")
    git(git_project, "merge", "--quiet", "--ff-only", "others")
    (git_project / "mine.txt").write_text("x\n")
    git(git_project, "add", "mine.txt")

    git(git_project, "commit", "--quiet", "--amend", "--no-edit")

    assert own_paths(git_project, base) == ("mine.txt",)


def test_an_uncounted_reflog_cannot_tell_which_commits_are_the_sessions(git_project: Path, base: str) -> None:
    commit(git_project, "mine.txt")

    with pytest.raises(ValueError, match="not counted"):
        own_paths(git_project, base, None)


def test_a_repository_without_a_reflog_cannot_tell_either(git_project: Path, base: str) -> None:
    git(git_project, "config", "core.logAllRefUpdates", "false")
    commit(git_project, "mine.txt")
    registered_entries = len(git(git_project, "reflog", "show", "--format=%H", "HEAD").splitlines())

    with pytest.raises(ValueError, match="no entry"):
        own_paths(git_project, base, registered_entries)


def test_a_commit_subject_with_a_unicode_line_break_does_not_split_its_reflog_entry(
    git_project: Path, base: str
) -> None:
    (git_project / "mine.txt").write_text("x\n")
    git(git_project, "add", "mine.txt")
    git(git_project, "commit", "--quiet", "-m", "split\x0bhere\x85now")

    assert own_paths(git_project, base) == ("mine.txt",)


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


def test_the_same_files_reached_by_cherry_pick_instead_of_fast_forward_are_a_new_review_input(
    git_project: Path, tmp_path: Path, executable: StubWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(executable, tmp_path, monkeypatch)
    record = register_session(git_project, tmp_path, monkeypatch)
    start = git(git_project, "rev-parse", "HEAD")
    others_work(git_project, "theirs.txt")
    git(git_project, "merge", "--quiet", "--ff-only", "others")
    fast_forwarded = model_rules_gate._inputs(record)

    git(git_project, "reset", "--quiet", "--hard", start)
    git(git_project, "cherry-pick", "others")

    assert model_rules_gate._inputs(record) != fast_forwarded


def test_a_discarded_commit_does_not_claim_a_path_that_an_outside_commit_then_changes(
    git_project: Path, base: str
) -> None:
    commit(git_project, "f.txt", "discarded\n")
    git(git_project, "reset", "--quiet", "--hard", base)
    others_work(git_project, "f.txt")

    git(git_project, "merge", "--quiet", "--ff-only", "others")

    assert own_paths(git_project, base, 1) == ()


def test_files_the_session_committed_in_a_repository_that_had_no_commit_are_still_judged(
    tmp_path: Path, executable: StubWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(executable, tmp_path, monkeypatch)
    empty = tmp_path / "empty"
    empty.mkdir()
    git(empty, "init", "--quiet", "-b", "main")
    for key, value in (("user.email", "t@example.invalid"), ("user.name", "T"), ("commit.gpgsign", "false")):
        git(empty, "config", key, value)
    record = register_session(empty, tmp_path, monkeypatch)
    commit(empty, "a.txt")

    assert "a.txt" in model_rules_gate._Changes.of(record).uncommitted.sendable


def test_a_session_whose_reflog_cannot_say_judges_every_commit_since_it_started_and_the_uncommitted_files(
    git_project: Path, tmp_path: Path, executable: StubWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(executable, tmp_path, monkeypatch)
    record = register_session(git_project, tmp_path, monkeypatch)
    baseline = record.directory / "baseline.json"
    baseline.write_text(json.dumps({**json.loads(baseline.read_text()), "reflog_entries": None}))
    others_work(git_project, "theirs.txt")
    git(git_project, "merge", "--quiet", "--ff-only", "others")
    commit(git_project, "committed.txt")
    edit(record, "after\n")

    changes = model_rules_gate._Changes.of(record)

    assert changes.committed.sendable == ("committed.txt", "theirs.txt")
    assert changes.uncommitted.sendable == ("notes.txt",)


def test_the_same_content_committed_or_left_uncommitted_is_a_new_review_input(
    git_project: Path, tmp_path: Path, executable: StubWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fakes(executable, tmp_path, monkeypatch)
    record = register_session(git_project, tmp_path, monkeypatch)
    start = git(git_project, "rev-parse", "HEAD")
    others_work(git_project, "theirs.txt")
    git(git_project, "merge", "--quiet", "--ff-only", "others")
    fast_forwarded = model_rules_gate._inputs(record)

    git(git_project, "reset", "--quiet", "--soft", start)

    assert model_rules_gate._inputs(record) != fast_forwarded
