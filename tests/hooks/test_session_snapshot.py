import hashlib
import os
import subprocess
from io import BufferedReader
from pathlib import Path

import pytest
from tests.runtime import load_script_module

snapshot = load_script_module("agents/hooks/lib/session_snapshot.py", "session_snapshot")


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    (root / "source.py").write_text("already dirty\n")
    (root / ".gitignore").write_text("output/\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    (root / "source.py").write_text("preexisting edit\n")
    return root


def test_start_state_excludes_preexisting_changes_without_a_commit_or_remote(repository: Path) -> None:
    baseline = snapshot.capture(repository)
    assert baseline.changed_paths(snapshot.capture(repository)) == ()
    assert "preexisting edit" not in str(baseline.to_json())


@pytest.mark.parametrize("change", ["edit", "add", "delete", "rename", "executable"])
def test_content_and_file_identity_changes_are_selected(repository: Path, change: str) -> None:
    baseline = snapshot.capture(repository)
    source = repository / "source.py"
    expected = ("source.py",)
    if change == "edit":
        source.write_text("task edit\n")
    elif change == "add":
        (repository / "new\n file.py").write_text("new\n")
        expected = ("new\n file.py",)
    elif change == "delete":
        source.unlink()
    elif change == "rename":
        source.rename(repository / "renamed.py")
        expected = ("renamed.py", "source.py")
    else:
        source.chmod(0o755)
    current = snapshot.capture(repository)
    assert baseline.changed_paths(current) == expected
    assert current.digest != baseline.digest


def test_generated_ignored_files_do_not_require_tests(repository: Path) -> None:
    baseline = snapshot.capture(repository)
    (repository / "output").mkdir()
    (repository / "output/result.py").write_text("generated")
    assert baseline.changed_paths(snapshot.capture(repository)) == ()


def test_restoring_content_restores_snapshot(repository: Path) -> None:
    baseline = snapshot.capture(repository)
    (repository / "source.py").write_text("temporary change\n")
    (repository / "source.py").write_text("preexisting edit\n")
    assert snapshot.capture(repository).digest == baseline.digest


def test_symlink_to_directory_is_recorded_by_link_text(repository: Path) -> None:
    (repository / "package").mkdir()
    (repository / "package/index.js").write_text("one")
    (repository / "cache_link").symlink_to("package")
    baseline = snapshot.capture(repository)
    assert dict(baseline.entries)["cache_link"] == "link:package"
    (repository / "package/index.js").write_text("two")
    assert "cache_link" not in baseline.changed_paths(snapshot.capture(repository))


def test_dangling_symlink_is_recorded_and_retargeting_is_detected(repository: Path) -> None:
    (repository / "dangling").symlink_to("missing")
    baseline = snapshot.capture(repository)
    assert dict(baseline.entries)["dangling"] == "link:missing"
    (repository / "dangling").unlink()
    (repository / "dangling").symlink_to("elsewhere")
    assert baseline.changed_paths(snapshot.capture(repository)) == ("dangling",)


def test_symlink_loop_does_not_fail_the_snapshot(repository: Path) -> None:
    (repository / "loop_a").symlink_to("loop_b")
    (repository / "loop_b").symlink_to("loop_a")
    assert dict(snapshot.capture(repository).entries)["loop_a"] == "link:loop_b"


def test_outside_symlink_is_recorded_without_reading_its_target(repository: Path, tmp_path: Path) -> None:
    target = tmp_path / "external.py"
    target.write_text("SECRET-PAYLOAD")
    (repository / "link.py").symlink_to(target)
    baseline = snapshot.capture(repository)
    assert dict(baseline.entries)["link.py"] == f"link:{target}"
    assert "SECRET-PAYLOAD" not in str(baseline.to_json())
    target.write_text("changed outside")
    assert baseline.changed_paths(snapshot.capture(repository)) == ()


def test_symlink_to_regular_file_in_worktree_detects_target_edits(repository: Path) -> None:
    (repository / "alias.py").symlink_to("source.py")
    baseline = snapshot.capture(repository)
    (repository / "source.py").write_text("task edit\n")
    assert baseline.changed_paths(snapshot.capture(repository)) == ("alias.py", "source.py")


def test_tracked_edit_is_detected_even_when_size_and_mtime_are_restored(repository: Path) -> None:
    source = repository / "source.py"
    before = source.stat()
    baseline = snapshot.capture(repository)
    source.write_text("PREEXISTING EDIT\n"[: before.st_size - 1] + "\n")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert baseline.changed_paths(snapshot.capture(repository)) == ("source.py",)


def test_untracked_edit_is_detected_even_when_size_and_mtime_are_restored(repository: Path) -> None:
    created = repository / "notes.txt"
    created.write_text("aaaa")
    before = created.stat()
    baseline = snapshot.capture(repository)
    created.write_text("bbbb")
    os.utime(created, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert baseline.changed_paths(snapshot.capture(repository)) == ("notes.txt",)


def hashed_paths(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    opened: list[str] = []
    real_digest = hashlib.file_digest

    def record(stream: BufferedReader, name: str) -> hashlib._Hash:
        opened.append(Path(stream.name).name)
        return real_digest(stream, name)

    monkeypatch.setattr(hashlib, "file_digest", record)
    return opened


def test_untracked_files_are_not_read(repository: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for index in range(200):
        (repository / f"artifact_{index}.bin").write_text("x" * 100)
    opened = hashed_paths(monkeypatch)
    snapshot.capture(repository)
    assert sorted(opened) == [".gitignore", "source.py"]


def test_large_tracked_file_is_not_read(repository: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    large = repository / "large.dat"
    large.write_bytes(b"x" * 64)
    subprocess.run(["git", "-C", str(repository), "add", "large.dat"], check=True)
    monkeypatch.setattr(snapshot, "HASH_LIMIT_BYTES", 32)
    baseline = snapshot.capture(repository)
    assert dict(baseline.entries)["large.dat"].startswith("stat:")
    large.write_bytes(b"y" * 65)
    assert baseline.changed_paths(snapshot.capture(repository)) == ("large.dat",)


def test_unreadable_tracked_file_does_not_fail_the_snapshot(repository: Path) -> None:
    source = repository / "source.py"
    source.chmod(0)
    try:
        baseline = snapshot.capture(repository)
        assert dict(baseline.entries)["source.py"].startswith("stat:")
    finally:
        source.chmod(0o644)


def test_fifo_does_not_block_or_fail_the_snapshot(repository: Path) -> None:
    os.mkfifo(repository / "pipe")
    assert "pipe" not in dict(snapshot.capture(repository).entries)


def test_untracked_nested_repository_is_not_read(repository: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = repository / "clone"
    subprocess.run(["git", "init", "--quiet", str(nested)], check=True)
    (nested / "a.py").write_text("one")
    opened = hashed_paths(monkeypatch)
    baseline = snapshot.capture(repository)
    assert "a.py" not in opened
    (nested / "a.py").write_text("two!")
    assert baseline.changed_paths(snapshot.capture(repository)) == ("clone/",)


def test_tracked_file_under_a_linked_parent_is_not_read_outside_the_worktree(repository: Path, tmp_path: Path) -> None:
    (repository / "package").mkdir()
    (repository / "package/data.py").write_text("inside")
    subprocess.run(["git", "-C", str(repository), "add", "package"], check=True)
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    (outside / "data.py").write_text("SECRET-PAYLOAD")
    (repository / "package/data.py").unlink()
    (repository / "package").rmdir()
    (repository / "package").symlink_to(outside)
    baseline = snapshot.capture(repository)
    assert dict(baseline.entries)["package/data.py"].startswith("escaped:")
    (outside / "data.py").write_text("changed outside")
    assert baseline.changed_paths(snapshot.capture(repository)) == ()


@pytest.mark.parametrize("tracked", [True, False])
def test_retargeting_a_link_to_look_like_a_signature_is_detected(repository: Path, tracked: bool) -> None:
    link = repository / "alias.py"
    link.symlink_to("source.py")
    if tracked:
        subprocess.run(["git", "-C", str(repository), "add", "alias.py"], check=True)
    baseline = snapshot.capture(repository)
    forged = dict(baseline.entries)["alias.py"].removeprefix("linkfile:")
    link.unlink()
    link.symlink_to(f"source.py:{forged}")
    assert baseline.changed_paths(snapshot.capture(repository)) == ("alias.py",)


def test_input_whose_metadata_cannot_be_read_fails_instead_of_hiding_edits(repository: Path) -> None:
    (repository / "private").mkdir()
    (repository / "private/data.py").write_text("one")
    subprocess.run(["git", "-C", str(repository), "add", "private"], check=True)
    (repository / "private").chmod(0)
    try:
        with pytest.raises(snapshot.SnapshotError, match="Cannot inspect"):
            snapshot.capture(repository)
    finally:
        (repository / "private").chmod(0o755)
