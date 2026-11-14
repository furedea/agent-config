"""rm runs unprompted inside the worktree and the session's temporary directories; elsewhere it asks."""

import os
from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")


def judged(project: Path | None, command: str, kind: str = "allowed") -> str:
    payload: dict = {"session_id": "session-a", "tool_name": "Bash", "tool_input": {"command": command}}
    if project is not None:
        payload["cwd"] = str(project)
    return guard.decide(kind, payload).decision


@pytest.mark.parametrize(
    "command",
    [
        "rm scratch.txt",
        "rm -f scratch.txt notes/old.md",
        "rm -fv scratch.txt",
        "rm -- -odd-name",
        "rm ./build/out.o",
        "rm -d empty-directory",
        "git status && rm scratch.txt",
        "/bin/rm scratch.txt",
        "command rm scratch.txt",
    ],
)
def test_removing_files_inside_the_worktree_runs_unprompted(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "allow"


def test_removing_a_file_in_the_session_temporary_directory_runs_unprompted(git_project: Path) -> None:
    temporary = Path(os.environ.get("TMPDIR", "/tmp")).resolve() / "scratch.txt"
    assert judged(git_project, f"rm -f {temporary}") == "allow"


def test_removing_a_symlink_inside_the_worktree_removes_only_the_link(git_project: Path) -> None:
    (git_project / "link").symlink_to(Path.home())
    assert judged(git_project, "rm link") == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "rm ~/.zshrc",
        "rm /etc/hosts",
        "rm ../../../../../../../../../../../../etc/hosts",
        "rm scratch.txt ~/.zshrc",
        "rm -f -- ~/.zshrc",
        "sudo rm scratch.txt ~/.zshrc",
        "nohup rm ~/.zshrc",
    ],
)
def test_removing_a_path_outside_the_worktree_and_temporary_directories_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


def test_removing_through_a_linked_directory_that_leaves_the_worktree_asks(git_project: Path) -> None:
    (git_project / "home").symlink_to(Path.home())
    assert judged(git_project, "rm home/.zshrc") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "rm .git/index",
        "rm .git",
        "rm -f .git/hooks/pre-commit",
        "rm sub/.git/HEAD",
        "rm .GIT/index",
        "rm ./.git/config",
    ],
)
def test_removing_git_metadata_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


def test_removing_git_metadata_reached_through_a_link_asks(git_project: Path) -> None:
    (git_project / "meta").symlink_to(git_project / ".git")
    assert judged(git_project, "rm meta/index") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "rm $TARGET",
        'rm "$TMPDIR/scratch.txt"',
        "rm *.txt",
        "rm $(cat list.txt)",
        "rm build/${NAME}.o",
        "ls | xargs rm",
    ],
)
def test_removing_a_path_known_only_at_run_time_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "cd / && rm etc/hosts",
        "(cd ~; rm .zshrc)",
        "pushd ~ && rm .zshrc",
        "popd && rm scratch.txt",
        "env -C / rm etc/hosts",
        "env --chdir=/ rm etc/hosts",
        "env -iC / rm etc/hosts",
    ],
)
def test_removal_after_a_directory_change_the_guard_cannot_follow_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "ln -s ~ home && rm home/.zshrc",
        "mkdir -p out && rm out/old.txt",
        "mv a b && rm b",
        "cp -R ~/.ssh keys; rm keys/config",
        "install -d out && rm out/x",
    ],
)
def test_removal_beside_a_command_that_can_create_links_or_directories_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


@pytest.mark.parametrize("command", ["rm -fR build", "rm -v -r build", "rm -dR build", "rm --recursive build"])
def test_recursive_removal_asks_even_in_forms_the_deny_prefixes_do_not_list(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


@pytest.mark.usefixtures("isolated_project")
def test_removal_asks_when_the_working_directory_is_unknown() -> None:
    assert judged(None, "rm scratch.txt") == "ask"


@pytest.mark.parametrize("command", ["rm -rf build", "rm -r build", "nohup rm -rf build"])
def test_recursive_removal_stays_denied(git_project: Path, command: str) -> None:
    assert judged(git_project, command, kind="forbidden") == "deny"


@pytest.mark.parametrize("command", ["echo rm ~/.zshrc", "git rm scratch.txt", "rmdir empty"])
def test_other_programs_are_not_judged_as_removal(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "allow"
