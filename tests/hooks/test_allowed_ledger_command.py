"""The fleet ledger CLI runs unprompted only in its documented forms, and hold never hides a command from review."""

import os
from pathlib import Path

import pytest

from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


def executable_ledger(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / "ledger"
    program.write_text("#!/bin/sh\n")
    program.chmod(0o755)
    return program


@pytest.fixture(autouse=True)
def installed_ledger(isolated_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand in for /usr/local/bin/ledger, found first on PATH like the real one."""
    installed = executable_ledger(isolated_project / "installed")
    monkeypatch.setattr(guard, "LEDGER_INSTALLED", installed)
    monkeypatch.setenv("PATH", f"{installed.parent}{os.pathsep}{os.environ['PATH']}")
    return installed


def verdict(kind: str, command: str) -> str:
    return guard.decide(kind, {"tool_input": {"command": command}}).decision


@pytest.mark.parametrize(
    "command",
    [
        "ledger ping",
        "ledger report --failure build-42",
        "ledger report --failure build-42 --body 'pytest failed in tests/test_x.py'",
        "ledger report --failure build-42 --request-id retry-1 --body report_text",
        "ledger claim --failure build-42",
        'ledger report --failure build-42 --body "pytest failed in tests"',
        'ledger result --failure build-42 --generation 3 --result "fixed by pinning"',
        "ledger claim --failure build-42 --request-id retry-1",
        "ledger status --failure build-42",
        "ledger release --failure build-42 --generation 3",
        "ledger result --failure build-42 --generation 3 --result fixed",
        "ledger result --failure build-42 --generation 3 --result 'fixed by pinning numpy'",
        "ledger hold --failure build-42 -- git status",
        "ledger hold --failure build-42 --refresh-seconds 2.5 --release-on-failure -- uv run --frozen pytest",
        "ledger hold --failure build-42 --request-id retry-1 -- nix flake check",
        "ledger hold --failure build-42 -- ledger ping",
        "echo 'body from a pipe' | ledger report --failure build-42",
        'ledger claim --failure "$FAILURE"',
    ],
)
def test_documented_ledger_forms_run_without_a_prompt(command: str) -> None:
    assert verdict("allowed", command) == "allow"
    assert verdict("forbidden", command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "ledger",
        "ledger frobnicate",
        "ledger ping --extra",
        "ledger ping now",
        "ledger report --failure build-42 --unknown value",
        "ledger report --failure=build-42",
        "ledger report --fail build-42",
        "ledger release --failure build-42 --generation three",
        "ledger result --failure build-42 --generation 3 --result",
        "ledger claim --failure build-42 extra",
        "ledger claim --failure 'a;b'",
        "ledger claim --failure ../build-42",
        "ledger claim --failure build-42 $EXTRA",
        "ledger --help",
    ],
)
def test_unlisted_or_malformed_ledger_forms_ask(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "ledger --spool-root /tmp/fake report --failure build-42",
        "ledger --spool-root=/tmp/fake ping",
        "ledger --timeout 600 ping",
        "ledger report --failure build-42 --spool-root /tmp/fake",
        "ledger hold --failure build-42 --spool-root /tmp/fake -- git status",
        "ledger --spool-root /tmp/fake hold --failure build-42 -- git status",
    ],
)
def test_ledger_options_that_move_the_spool_or_slow_the_answer_ask(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "./ledger ping",
        "/tmp/ledger ping",
        "bin/ledger report --failure build-42",
    ],
)
def test_only_the_installed_ledger_program_runs_without_a_prompt(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "ledger report --failure build-42 --body `id`",
        "ledger report --failure build-42 --body *",
    ],
)
def test_ledger_with_computed_words_asks(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "ledger hold --failure build-42 -- rm -rf build",
        "ledger hold --failure build-42 -- git add .",
        "ledger hold --failure build-42 -- docker push image",
        "ledger hold --failure build-42 -- timeout 5 rm -rf build",
        "ledger hold --failure build-42 -- env nice rm -rf build",
        "ledger hold --failure build-42 -- ledger hold --failure other -- rm -rf build",
    ],
)
def test_hold_does_not_hide_a_forbidden_command(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "ledger hold --failure build-42 -- rm build/output.txt",
        "ledger hold --failure build-42 -- pip install requests",
        "ledger hold --failure build-42 -- unknown-tool --flag",
        "ledger hold --failure build-42 -- bash -c 'make all'",
        "ledger hold --failure build-42 -- sh script.sh",
        "ledger hold --failure build-42 -- timeout 5 unknown-tool",
        "ledger hold --failure build-42 -- gh pr merge 1",
        "ledger hold --failure build-42 -- gh api -H 'Accept: x' repos/o/r",
        "ledger hold --failure build-42 -- curl https://example.com/",
        "ledger hold --failure build-42 -- docker run image",
        "ledger hold --failure build-42 -- go run example.com/tool@latest",
        "ledger hold --failure build-42 -- nix run nixpkgs#hello",
    ],
)
def test_hold_asks_for_every_command_that_would_not_run_on_its_own(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "ledger hold --failure build-42",
        "ledger hold --failure build-42 --",
        "ledger hold --failure build-42 git status",
        "ledger hold --failure build-42 --release-on-failure",
        "ledger hold --failure build-42 --unknown -- git status",
        "ledger hold --failure=build-42 -- git status",
        "ledger hold --fail build-42 -- git status",
    ],
)
def test_hold_without_the_documented_options_and_separator_asks(command: str) -> None:
    assert verdict("allowed", command) == "ask"


def test_a_command_chained_after_a_ledger_call_is_still_judged() -> None:
    assert verdict("allowed", "ledger ping && rm build/output.txt") == "allow"
    assert verdict("allowed", "ledger ping && ledger frobnicate") == "ask"
    assert verdict("forbidden", "ledger ping && git add .") == "deny"


def test_the_installed_ledger_runs_by_its_own_path(installed_ledger: Path) -> None:
    assert verdict("allowed", f"{installed_ledger} ping") == "allow"


def test_a_ledger_earlier_on_path_than_the_installed_one_asks(
    isolated_project: Path, installed_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shadow = executable_ledger(isolated_project / "shadow")
    monkeypatch.setenv("PATH", f"{shadow.parent}{os.pathsep}{os.environ['PATH']}")
    assert verdict("allowed", "ledger ping") == "ask"
    assert verdict("allowed", f"{installed_ledger} ping") == "allow"


def test_a_ledger_in_the_working_directory_asks(isolated_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executable_ledger(isolated_project)
    monkeypatch.setenv("PATH", f".{os.pathsep}{os.environ['PATH']}")
    assert verdict("allowed", "ledger ping") == "ask"
    assert verdict("allowed", "./ledger ping") == "ask"


def test_without_an_installed_ledger_nothing_runs_unprompted(
    isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guard, "LEDGER_INSTALLED", isolated_project / "missing/ledger")
    assert verdict("allowed", "ledger ping") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "PATH=/tmp/shadow ledger ping",
        "PATH=/tmp/shadow:$PATH ledger report --failure build-42",
        "FOO=1 ledger ping",
        "env PATH=/tmp/shadow ledger ping",
        "env -i PATH=/tmp/shadow ledger ping",
        "ledger hold --failure build-42 -- env PATH=/tmp/shadow ledger ping",
        "ledger hold --failure build-42 -- git status && PATH=/tmp/shadow ledger ping",
    ],
)
def test_an_environment_assignment_before_ledger_asks(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "ledger hold --failure build-42 -- /tmp/git status",
        "ledger hold --failure build-42 -- ./git status",
        "ledger hold --failure build-42 -- /usr/bin/git status",
        "ledger hold --failure build-42 -- env /tmp/git status",
        "ledger hold --failure build-42 -- bash -n +n -c 'gh pr merge 1 --squash'",
        "ledger hold --failure build-42 -- bash -n +n -c 'rm build/output.txt'",
        "ledger hold --failure build-42 -- timeout 5 bash -n +n -c 'rm build/output.txt'",
    ],
)
def test_hold_neither_trusts_a_command_path_nor_loses_track_of_a_reparsed_script(command: str) -> None:
    assert verdict("allowed", command) == "ask"
