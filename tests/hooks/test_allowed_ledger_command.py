"""The fleet ledger CLI runs unprompted only in its documented forms, and hold never hides a command from review."""

import pytest

from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


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
        "ledger claim --failure build-42 --request-id retry-1",
        "ledger status --failure build-42",
        "ledger release --failure build-42 --generation 3",
        "ledger result --failure build-42 --generation 3 --result fixed",
        "ledger result --failure build-42 --generation 3 --result 'fixed by pinning numpy'",
        "ledger hold --failure build-42 -- git status",
        "ledger hold --failure build-42 --refresh-seconds 2.5 --release-on-failure -- uv run --frozen pytest",
        "ledger hold --failure build-42 --request-id retry-1 -- nix flake check",
        "ledger hold --failure build-42 -- ledger ping",
        "/usr/local/bin/ledger ping",
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
