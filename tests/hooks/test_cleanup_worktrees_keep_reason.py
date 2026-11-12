"""A merged branch's worktree that fails the safety check is kept with the reason on its own line."""

import shutil
from pathlib import Path

import cleanup_worktrees
import pytest
from tests.hooks.cleanup_worktrees_runtime import cleanup, git, task_worktree


def merged_lane(primary: Path, merged: dict[str, str], branch: str = "feat/done") -> Path:
    path = task_worktree(primary, branch)
    merged[branch] = git("rev-parse", "HEAD", cwd=path)
    return path


def keep_lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith("keep worktree ")]


def lane_of(primary: Path, path: Path) -> cleanup_worktrees.Worktree:
    return next(tree for tree in cleanup_worktrees.linked_worktrees(primary) if tree.path == path.resolve())


def admin_of(worktree: cleanup_worktrees.Worktree) -> Path:
    assert worktree.admin_dir is not None
    return worktree.admin_dir


def test_uncommitted_changes_are_reported_as_the_reason(primary: Path, merged: dict[str, str]) -> None:
    path = merged_lane(primary, merged)
    (path / "README.md").write_text("edited\n")

    result = cleanup(primary)

    assert keep_lines(result.stdout) == [f"keep worktree {path.resolve()}: uncommitted changes"]
    assert path.exists()


def test_a_gitlink_is_reported_as_the_reason(primary: Path, merged: dict[str, str]) -> None:
    path = task_worktree(primary, "feat/done")
    git("update-index", "--add", "--cacheinfo", f"160000,{git('rev-parse', 'HEAD', cwd=path)},submodule", cwd=path)
    git("commit", "--quiet", "-m", "Add gitlink", cwd=path)
    merged["feat/done"] = git("rev-parse", "HEAD", cwd=path)

    result = cleanup(primary)

    assert keep_lines(result.stdout) == [f"keep worktree {path.resolve()}: submodule entry"]


def test_a_per_worktree_config_is_reported_as_the_reason(primary: Path, merged: dict[str, str]) -> None:
    path = merged_lane(primary, merged)
    admin = Path(git("rev-parse", "--absolute-git-dir", cwd=path))
    (admin / "config.worktree").write_text("[core]\n\tbare = false\n")

    result = cleanup(primary)

    assert keep_lines(result.stdout) == [f"keep worktree {path.resolve()}: config.worktree is present"]


def test_a_foreign_commondir_is_reported_as_the_reason(primary: Path, merged: dict[str, str], tmp_path: Path) -> None:
    path = merged_lane(primary, merged)
    admin = Path(git("rev-parse", "--absolute-git-dir", cwd=path))
    fake = tmp_path / "writable/fake.git"
    shutil.copytree(primary / ".git", fake)
    (admin / "commondir").write_text(str(fake))

    result = cleanup(primary)

    assert keep_lines(result.stdout) == [f"keep worktree {path.resolve()}: commondir does not point at the primary"]


def test_a_replaced_git_file_is_reported_as_the_reason(primary: Path, merged: dict[str, str], tmp_path: Path) -> None:
    path = merged_lane(primary, merged)
    fake = tmp_path / "writable/fake"
    fake.parent.mkdir()
    git("clone", "--quiet", "--no-checkout", str(primary), str(fake), cwd=primary)
    (path / ".git").write_text(f"gitdir: {fake / '.git'}\n")

    result = cleanup(primary)

    assert keep_lines(result.stdout) == [
        f"keep worktree {path.resolve()}: .git file does not point at the admin directory"
    ]


def test_a_gitdir_that_points_elsewhere_is_reported_as_the_reason(
    primary: Path, merged: dict[str, str], tmp_path: Path
) -> None:
    path = merged_lane(primary, merged)
    worktree = lane_of(primary, path)
    (admin_of(worktree) / "gitdir").write_text(str(tmp_path / "elsewhere/.git"))

    assert cleanup_worktrees.worktree_blocker(primary, worktree) == "gitdir does not point back at the worktree"


def test_a_worktree_without_an_admin_directory_is_reported_as_the_reason(
    primary: Path, merged: dict[str, str]
) -> None:
    path = merged_lane(primary, merged)
    unverifiable = cleanup_worktrees.Worktree(path.resolve(), "feat/done", None)

    assert cleanup_worktrees.worktree_blocker(primary, unverifiable) == "no admin directory registered for it"


def test_a_missing_admin_file_is_reported_as_the_reason(primary: Path, merged: dict[str, str]) -> None:
    path = merged_lane(primary, merged)
    worktree = lane_of(primary, path)
    (admin_of(worktree) / "commondir").unlink()

    assert cleanup_worktrees.worktree_blocker(primary, worktree) == "admin directory cannot be read"


def test_a_clean_worktree_has_no_blocker(primary: Path, merged: dict[str, str]) -> None:
    path = merged_lane(primary, merged)

    assert cleanup_worktrees.worktree_blocker(primary, lane_of(primary, path)) is None


@pytest.mark.parametrize("change", ["later commit", "open pull request"])
def test_an_unmerged_worktree_is_kept_silently(primary: Path, merged: dict[str, str], change: str) -> None:
    path = task_worktree(primary, "feat/busy")
    if change == "later commit":
        merged["feat/busy"] = git("rev-parse", "HEAD", cwd=path)
        (path / "more.txt").write_text("more\n")
        git("add", "more.txt", cwd=path)
        git("commit", "--quiet", "-m", "more", cwd=path)
    (path / "README.md").write_text("edited\n")

    result = cleanup(primary)

    assert keep_lines(result.stdout) == []


def test_every_kept_worktree_is_reported_beside_the_ignored_files_reason(
    primary: Path, merged: dict[str, str]
) -> None:
    dirty = merged_lane(primary, merged, "feat/dirty")
    (dirty / "README.md").write_text("edited\n")
    ignored = merged_lane(primary, merged, "feat/ignored")
    (ignored / ".gitignore").write_text("*.ignored\n")
    git("add", ".gitignore", cwd=ignored)
    git("commit", "--quiet", "-m", "ignore", cwd=ignored)
    merged["feat/ignored"] = git("rev-parse", "HEAD", cwd=ignored)
    (ignored / "notes.ignored").write_text("x\n")

    lines = keep_lines(cleanup(primary).stdout)

    assert sorted(lines) == sorted(
        [
            f"keep worktree {dirty.resolve()}: uncommitted changes",
            f"keep worktree {ignored.resolve()}: ignored files would be lost: notes.ignored",
        ]
    )
