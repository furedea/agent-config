"""rm runs unprompted inside the worktree and the session's temporary directories; elsewhere it asks."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest
from tests.hooks.system_programs import system_programs, trust_directory, use_own_program, use_system_programs
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")


@pytest.fixture(autouse=True)
def system_rm(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """rm and the external wrappers resolve to root-owned system programs, as on a deployed machine."""
    for name in [name for name in os.environ if name.startswith(("LD_", "DYLD_", "BASH_FUNC_"))]:
        monkeypatch.delenv(name)
    for name in ("BASH_ENV", "ENV"):
        monkeypatch.delenv(name, raising=False)
    directory = tmp_path_factory.mktemp("system") / "bin"
    use_system_programs(directory, monkeypatch, "rm", "nohup", "nice", "timeout", "stdbuf")
    trust_directory(directory, monkeypatch)


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
        "echo start && rm scratch.txt",
        "rm scratch.txt; echo done",
        "nohup rm scratch.txt",
        "/bin/rm scratch.txt",
        "command rm scratch.txt",
    ],
)
def test_removing_files_inside_the_worktree_runs_unprompted(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "allow"


def test_removing_a_file_in_the_session_temporary_directory_runs_unprompted(
    git_project: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = tmp_path_factory.mktemp("session-tmp") / f"claude-{os.getuid()}"
    session.mkdir()
    monkeypatch.setenv("CLAUDE_CODE_TMPDIR", str(session.parent))
    assert judged(git_project, f"rm -f {session.resolve()}/scratch.txt") == "allow"


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
        "cd .git && rm -f index",
        "cd .. && rm sibling.txt",
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
        "git status && rm scratch.txt",
        "builtin cd / && rm etc/hosts",
        "gcp -R ~/.ssh keys && rm keys/config",
        "python3 make_link.py && rm home/.zshrc",
        "$TOOL && rm scratch.txt",
        "./ls && rm scratch.txt",
        "PATH=. ls && rm scratch.txt",
        "env PATH=. ls && rm scratch.txt",
        "BASH_ENV=x true && rm scratch.txt",
        "printf -v PATH evil && rm scratch.txt",
        "ls && rm safe/.zshrc",
        "cat notes && rm scratch.txt",
    ],
)
def test_removal_beside_a_program_not_listed_as_read_only_asks(git_project: Path, command: str) -> None:
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


@pytest.mark.parametrize("command", ["rm '~zz/x' ~/.zshrc", "rm '~nosuchuser/x' /etc/hosts"])
def test_a_quoted_tilde_operand_does_not_stop_the_check(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


def test_a_quoted_tilde_names_a_file_in_the_working_directory(git_project: Path) -> None:
    assert judged(git_project, "rm '~/notes'") == "allow"


@pytest.mark.parametrize("shared", ["/tmp", "/var/tmp"])
def test_a_shared_system_temporary_directory_is_not_a_session_root(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, shared: str
) -> None:
    for name in ("TMPDIR", "CLAUDE_TMPDIR", "CLAUDE_CODE_TMPDIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(tempfile, "tempdir", shared)
    assert judged(git_project, f"rm {shared}/other-app.sock") == "ask"


def test_a_session_temporary_directory_below_a_shared_root_stays_writable(
    git_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = Path(f"/tmp/claude-{os.getuid()}").resolve()
    monkeypatch.setenv("TMPDIR", str(session))
    monkeypatch.setattr(tempfile, "tempdir", str(session))
    assert judged(git_project, f"rm {session}/scratch.txt") == "allow"
    assert judged(git_project, "rm /tmp/other-app.sock") == "ask"


def test_the_per_user_system_temporary_directory_is_not_a_session_root(
    git_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = "/private/var/folders/ab/cd1234/T"
    for name in ("CLAUDE_TMPDIR", "CLAUDE_CODE_TMPDIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TMPDIR", shared)
    monkeypatch.setattr(tempfile, "tempdir", shared)
    assert judged(git_project, f"rm {shared}/other-app.sock") == "ask"


@pytest.mark.parametrize("value", ["/", "~/.tmp", "/Users/shared-tmp"])
def test_a_general_tmpdir_is_not_a_session_root(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    for name in ("CLAUDE_TMPDIR", "CLAUDE_CODE_TMPDIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TMPDIR", value)
    target = Path(value).expanduser().resolve() / "other-session-file"
    assert judged(git_project, f"rm {target}") == "ask"


def test_the_claude_session_tmpdir_is_a_session_root(git_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CLAUDE_TMPDIR", "CLAUDE_CODE_TMPDIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TMPDIR", f"/tmp/claude-{os.getuid()}")
    assert judged(git_project, f"rm {Path(f'/tmp/claude-{os.getuid()}').resolve()}/scratch.txt") == "allow"


@pytest.mark.parametrize("name", ["rm", "nohup"])
def test_a_program_found_in_a_directory_the_session_writes_asks(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    use_own_program(git_project / ".venv" / "bin", monkeypatch, name)
    command = "rm scratch.txt" if name == "rm" else "nohup rm scratch.txt"
    assert judged(git_project, command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "PATH=.venv/bin rm scratch.txt",
        "LD_PRELOAD=./x.so rm scratch.txt",
        "rmx=1 rm scratch.txt",
        "PATH=.venv/bin; rm scratch.txt",
        "export PATH=.venv/bin; rm scratch.txt",
        "LD_PRELOAD=./x.so; rm scratch.txt",
    ],
)
def test_an_rm_whose_program_the_command_can_change_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


def test_a_link_to_a_system_program_in_a_directory_the_session_writes_asks(
    git_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_system_programs(git_project / ".venv" / "bin", monkeypatch, "rm")
    assert judged(git_project, "rm scratch.txt") == "ask"


@pytest.mark.parametrize("command", ["./bin/rm scratch.txt", "bin/rm scratch.txt"])
def test_an_rm_named_by_a_relative_path_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


def test_a_relative_path_entry_makes_rm_ask(git_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", f"bin{os.pathsep}{os.environ['PATH']}")
    assert judged(git_project, "rm scratch.txt") == "ask"


def test_a_builtin_name_behind_an_external_wrapper_is_looked_up_on_path(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    without_session_temporary_roots(monkeypatch)
    use_own_program(tmp_path_factory.mktemp("user-bin"), monkeypatch, "echo")
    assert judged(git_project, "echo hi && rm scratch.txt") == "allow"
    assert judged(git_project, "nohup echo hi && rm scratch.txt") == "ask"


def test_a_root_session_trusts_no_program_by_its_owner(git_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system_programs.os, "geteuid", lambda: 0)
    assert judged(git_project, "rm scratch.txt") == "ask"


@pytest.mark.parametrize("name", ["BASH_FUNC_rm%%", "BASH_FUNC_echo%%", "BASH_FUNC_rm()", "BASH_ENV", "ENV"])
def test_an_inherited_shell_function_asks(git_project: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(name, "() {  /bin/rm -rf ~; }")
    assert judged(git_project, "echo hi && rm scratch.txt") == "ask"


def test_a_path_directory_linked_to_a_system_directory_asks(
    git_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (git_project / "bin").symlink_to(Path("/bin").resolve())
    monkeypatch.setenv("PATH", f"{git_project / 'bin'}{os.pathsep}{os.environ['PATH']}")
    assert judged(git_project, "rm scratch.txt") == "ask"


@pytest.mark.parametrize("command", ["rm {x,~/.zshrc}", "rm a{,/../../../../etc/hosts}", "rm {a,b}.txt"])
def test_an_operand_brace_expansion_can_spread_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


def test_a_git_worktree_setting_cannot_widen_the_worktree(git_project: Path) -> None:
    subprocess.run(["git", "config", "core.worktree", "/"], cwd=git_project, check=True)
    assert judged(git_project, "rm /etc/hosts") == "ask"
    assert judged(git_project, "rm scratch.txt") == "allow"


@pytest.mark.usefixtures("isolated_project")
def test_a_planted_git_directory_outside_the_worktree_does_not_widen_it(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    without_session_temporary_roots(monkeypatch)
    outside = tmp_path_factory.mktemp("planted")
    (outside / ".git" / "objects").mkdir(parents=True)
    (outside / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (outside / "work").mkdir()
    assert judged(outside / "work", f"rm {outside}/victim.txt") == "ask"


@pytest.mark.usefixtures("isolated_project")
def test_a_git_file_without_a_git_directory_is_not_a_worktree(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    without_session_temporary_roots(monkeypatch)
    outside = tmp_path_factory.mktemp("gitfile")
    (outside / ".git").write_text("gitdir: /nowhere\n")
    assert judged(outside, f"rm {outside}/victim.txt") == "ask"


def without_session_temporary_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave no temporary directory that could count as the session's, so only the worktree is writable."""
    for name in ("CLAUDE_TMPDIR", "CLAUDE_CODE_TMPDIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TMPDIR", "/nonexistent-session-tmp")


def test_a_broad_claude_code_tmpdir_is_not_a_session_root(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    without_session_temporary_roots(monkeypatch)
    broad = tmp_path_factory.mktemp("user-tmp")
    (broad / f"claude-{os.getuid()}").mkdir()
    monkeypatch.setenv("CLAUDE_CODE_TMPDIR", str(broad))
    assert judged(git_project, f"rm {broad.resolve()}/unrelated.txt") == "ask"
    assert judged(git_project, f"rm {broad.resolve()}/claude-{os.getuid()}/scratch.txt") == "allow"


@pytest.mark.parametrize("name", ["LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH"])
def test_an_inherited_loader_setting_asks(git_project: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(name, "/tmp/evil.so")
    assert judged(git_project, "rm scratch.txt") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "echo $((PATH=0)) && rm scratch.txt",
        "((PATH=0)); rm scratch.txt",
        "let PATH=0; rm scratch.txt",
        "echo ${x[PATH=1]} && rm scratch.txt",
        "echo ${PATH:=evil} && rm scratch.txt",
        "rm scratch.txt 2>${PATH:=evil}",
        "rm scratch.txt <<< ${PATH:=evil}",
        "echo hi > $((PATH=1)) && rm scratch.txt",
    ],
)
def test_an_arithmetic_assignment_beside_rm_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


@pytest.mark.parametrize("command", ["'' ; cd ~ ; rm .bashrc", '"" ; cd ~ ; rm .bashrc'])
def test_an_empty_program_name_does_not_hide_later_segments(git_project: Path, command: str) -> None:
    assert judged(git_project, command) == "ask"


def test_another_sessions_claude_directory_is_not_a_root(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    without_session_temporary_roots(monkeypatch)
    parent = tmp_path_factory.mktemp("shared-parent")
    (parent / f"claude-{os.getuid()}").mkdir()
    (parent / "claude-other").mkdir()
    monkeypatch.setenv("CLAUDE_CODE_TMPDIR", str(parent))
    assert judged(git_project, f"rm {parent.resolve()}/claude-other/file") == "ask"


def test_a_writable_path_entry_before_the_system_rm_asks(git_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    early = git_project / ".venv" / "bin"
    early.mkdir(parents=True)
    monkeypatch.setenv("PATH", f"{early}{os.pathsep}{os.environ['PATH']}")
    assert judged(git_project, "rm scratch.txt") == "ask"
