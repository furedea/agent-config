"""The fleet ledger CLI runs unprompted only as the installed program in its documented forms, and hold never hides a command."""

import os
from pathlib import Path

import pytest

from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")
INSTALLED: list[Path] = []


def executable_ledger(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / "ledger"
    program.write_text("#!/bin/sh\n")
    program.chmod(0o755)
    return program


@pytest.fixture(autouse=True)
def installed_ledger(isolated_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand in for /usr/local/bin/ledger, which `@ledger` names in the commands below."""
    installed = executable_ledger(isolated_project / "installed")
    monkeypatch.setattr(guard, "LEDGER_INSTALLED", installed)
    INSTALLED[:] = [installed]
    return installed


def verdict(kind: str, command: str) -> str:
    command = command.replace("@ledger", str(INSTALLED[0]))
    return guard.decide(kind, {"tool_input": {"command": command}}).decision


@pytest.mark.parametrize(
    "command",
    [
        "@ledger ping",
        "@ledger report --failure build-42",
        "@ledger report --failure build-42 --body 'pytest failed in tests/test_x.py'",
        '@ledger report --failure build-42 --body "pytest failed in tests"',
        "@ledger report --failure build-42 --request-id retry-1 --body report_text",
        "@ledger claim --failure build-42",
        "@ledger claim --failure build-42 --request-id retry-1",
        "@ledger status --failure build-42",
        "@ledger release --failure build-42 --generation 3",
        "@ledger result --failure build-42 --generation 3 --result fixed",
        "@ledger result --failure build-42 --generation 3 --result 'fixed by pinning numpy'",
        '@ledger result --failure build-42 --generation 3 --result "fixed by pinning"',
        "@ledger hold --failure build-42 -- git status",
        "@ledger hold --failure build-42 --refresh-seconds 2.5 --release-on-failure -- uv run --frozen pytest",
        "@ledger hold --failure build-42 --request-id retry-1 -- nix flake check",
        '@ledger claim --failure "$FAILURE"',
    ],
)
def test_documented_ledger_forms_run_without_a_prompt(command: str) -> None:
    assert verdict("allowed", command) == "allow"
    assert verdict("forbidden", command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "@ledger",
        "@ledger frobnicate",
        "@ledger ping --extra",
        "@ledger ping now",
        "@ledger report --failure build-42 --unknown value",
        "@ledger report --failure=build-42",
        "@ledger report --fail build-42",
        "@ledger release --failure build-42 --generation three",
        "@ledger result --failure build-42 --generation 3 --result",
        "@ledger claim --failure build-42 extra",
        "@ledger claim --failure 'a;b'",
        "@ledger claim --failure ../build-42",
        "@ledger claim --failure build-42 $EXTRA",
        "@ledger --help",
        "@ledger report --failure build-42 --body `id`",
        "@ledger report --failure build-42 --body *",
    ],
)
def test_unlisted_or_malformed_ledger_forms_ask(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "@ledger --spool-root /tmp/fake report --failure build-42",
        "@ledger --spool-root=/tmp/fake ping",
        "@ledger --timeout 600 ping",
        "@ledger report --failure build-42 --spool-root /tmp/fake",
        "@ledger hold --failure build-42 --spool-root /tmp/fake -- git status",
        "@ledger --spool-root /tmp/fake hold --failure build-42 -- git status",
    ],
)
def test_ledger_options_that_move_the_spool_or_slow_the_answer_ask(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "ledger ping",
        "ledger report --failure build-42",
        "./ledger ping",
        "bin/ledger report --failure build-42",
        "/tmp/ledger ping",
        "/usr/local/bin/ledger ping",
    ],
)
def test_the_bare_name_and_every_other_path_ask(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "PATH=/tmp/shadow @ledger ping",
        "PATH=/tmp/shadow command @ledger ping",
        "PATH=/tmp/shadow exec @ledger ping",
        "PATH=/tmp/shadow env @ledger ping",
        "LD_PRELOAD=/tmp/x.so @ledger ping",
        "PYTHONPATH=/tmp/x @ledger ping",
        "FOO=1 @ledger ping",
        "env PATH=/tmp/shadow @ledger ping",
        "env -i @ledger ping",
        "command @ledger ping",
        "exec @ledger ping",
        "nohup @ledger ping",
        "nice @ledger ping",
        "timeout 5 @ledger ping",
        "xargs @ledger ping",
        "@ledger hold --failure build-42 -- env PATH=/tmp/shadow @ledger ping",
        "@ledger hold --failure build-42 -- @ledger ping",
    ],
)
def test_an_assignment_or_wrapper_before_ledger_asks(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "PATH=/tmp/shadow; @ledger ping",
        "export PATH=/tmp/shadow && @ledger ping",
        "export LD_PRELOAD=/tmp/x.so; @ledger ping",
        "hash -p /tmp/shadow/ledger ledger; @ledger ping",
        "cd /tmp/shadow && @ledger ping",
        "git status && @ledger ping",
        "@ledger ping && git status",
        "@ledger ping; @ledger ping",
        "echo body | @ledger report --failure build-42",
        "@ledger ping | cat",
        "@ledger ping &",
        "! @ledger ping",
        "( @ledger ping )",
        "{ @ledger ping; }",
        "if true; then @ledger ping; fi",
        "@ledger ping > /tmp/out",
        "bash -c '@ledger ping'",
        "sh -c 'PATH=/tmp/shadow @ledger ping'",
        "@ledger hold --failure build-42 -- bash -c 'PATH=/tmp/shadow; ledger ping'",
    ],
)
def test_ledger_sharing_a_line_with_another_statement_or_a_shell_asks(command: str) -> None:
    assert verdict("allowed", command) == "ask"


def test_a_shadow_earlier_on_path_cannot_change_what_the_absolute_path_runs(
    isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shadow = executable_ledger(isolated_project / "shadow")
    monkeypatch.setenv("PATH", f"{shadow.parent}{os.pathsep}{os.environ['PATH']}")
    assert verdict("allowed", "ledger ping") == "ask"
    assert verdict("allowed", "@ledger ping") == "allow"


def test_a_ledger_in_the_working_directory_asks(isolated_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executable_ledger(isolated_project)
    monkeypatch.setenv("PATH", f".{os.pathsep}{os.environ['PATH']}")
    assert verdict("allowed", "ledger ping") == "ask"
    assert verdict("allowed", "./ledger ping") == "ask"


def test_a_missing_ledger_asks(installed_ledger: Path) -> None:
    installed_ledger.unlink()
    assert verdict("allowed", "@ledger ping") == "ask"


def test_a_ledger_that_is_not_executable_asks(installed_ledger: Path) -> None:
    installed_ledger.chmod(0o644)
    assert verdict("allowed", "@ledger ping") == "ask"


def test_a_directory_in_place_of_ledger_asks(installed_ledger: Path) -> None:
    installed_ledger.unlink()
    installed_ledger.mkdir()
    assert verdict("allowed", "@ledger ping") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "@ledger hold --failure build-42 -- rm -rf build",
        "@ledger hold --failure build-42 -- git add .",
        "@ledger hold --failure build-42 -- docker push image",
        "@ledger hold --failure build-42 -- timeout 5 rm -rf build",
        "@ledger hold --failure build-42 -- env nice rm -rf build",
    ],
)
def test_hold_does_not_hide_a_forbidden_command(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "@ledger hold --failure build-42 -- rm build/output.txt",
        "@ledger hold --failure build-42 -- pip install requests",
        "@ledger hold --failure build-42 -- unknown-tool --flag",
        "@ledger hold --failure build-42 -- bash -c 'make all'",
        "@ledger hold --failure build-42 -- sh script.sh",
        "@ledger hold --failure build-42 -- timeout 5 unknown-tool",
        "@ledger hold --failure build-42 -- gh pr merge 1",
        "@ledger hold --failure build-42 -- gh api -H 'Accept: x' repos/o/r",
        "@ledger hold --failure build-42 -- curl https://example.com/",
        "@ledger hold --failure build-42 -- docker run image",
        "@ledger hold --failure build-42 -- go run example.com/tool@latest",
        "@ledger hold --failure build-42 -- nix run nixpkgs#hello",
    ],
)
def test_hold_asks_for_every_command_that_would_not_run_on_its_own(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "@ledger hold --failure build-42",
        "@ledger hold --failure build-42 --",
        "@ledger hold --failure build-42 git status",
        "@ledger hold --failure build-42 --release-on-failure",
        "@ledger hold --failure build-42 --unknown -- git status",
        "@ledger hold --failure=build-42 -- git status",
        "@ledger hold --fail build-42 -- git status",
    ],
)
def test_hold_without_the_documented_options_and_separator_asks(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "@ledger hold --failure build-42 -- /tmp/git status",
        "@ledger hold --failure build-42 -- ./git status",
        "@ledger hold --failure build-42 -- /usr/bin/git status",
        "@ledger hold --failure build-42 -- env /tmp/git status",
        "@ledger hold --failure build-42 -- bash -n +n -c 'gh pr merge 1 --squash'",
        "@ledger hold --failure build-42 -- bash -n +n -c 'rm build/output.txt'",
        "@ledger hold --failure build-42 -- timeout 5 bash -n +n -c 'rm build/output.txt'",
    ],
)
def test_hold_neither_trusts_a_command_path_nor_loses_track_of_a_reparsed_script(command: str) -> None:
    assert verdict("allowed", command) == "ask"
