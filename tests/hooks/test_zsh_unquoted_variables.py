"""When the executing shell is zsh, an unquoted variable is judged as the one word zsh runs (ADR-0022)."""

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


def decision(command: str, **payload: object) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}, **payload}).decision


@pytest.fixture
def zsh(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    request.getfixturevalue("isolated_project")
    monkeypatch.setenv("SHELL", "/bin/zsh")


run_by_zsh = pytest.mark.usefixtures("zsh")


@run_by_zsh
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh run view 42853069590 --job $J --log", id="an unquoted job id"),
        pytest.param("gh run view 42853069590 --job ${J} --log", id="a braced unquoted job id"),
        pytest.param("gh pr edit 438 --body-file $TMPDIR/body.md", id="an unquoted body file path"),
        pytest.param("gh pr edit 438 --body-file ${TMPDIR}/body.md", id="a braced unquoted body file path"),
        pytest.param('gh run view 1 --job "$J" --log', id="a quoted job id, unchanged"),
        pytest.param("export X=$Y; gh run view 1 --job $J --log", id="an export before the call"),
        pytest.param("gh run view 1 --job $J --log | head -20", id="a pipe after the call"),
        pytest.param("gh run view 1 --job $J --log 2>&1 && echo done", id="redirects and && around the call"),
    ],
)
def test_zsh_runs_an_unquoted_variable_as_one_word(command: str) -> None:
    assert decision(command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh run view 1 --job $J --log", id="an unquoted job id"),
        pytest.param("gh pr edit 438 --body-file $TMPDIR/body.md", id="an unquoted body file path"),
    ],
)
@pytest.mark.parametrize(
    "environment",
    [
        pytest.param({"SHELL": "/bin/bash"}, id="bash"),
        pytest.param({"SHELL": "/bin/zsh", "CLAUDE_CODE_SHELL": "/bin/bash"}, id="a shell chosen for Claude Code"),
        pytest.param({}, id="an unknown shell"),
    ],
)
def test_an_unquoted_variable_asks_unless_the_shell_is_known_to_be_zsh(
    monkeypatch: pytest.MonkeyPatch, command: str, environment: dict[str, str]
) -> None:
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    assert decision(command) == "ask"


@run_by_zsh
@pytest.mark.parametrize("provider", ["codex", "devin", "hermes", "pi", "dsh"])
def test_an_unquoted_variable_asks_for_a_provider_whose_shell_is_unconfirmed(provider: str) -> None:
    assert decision("gh run view 1 --job $J --log", provider=provider) == "ask"


@run_by_zsh
def test_a_claude_payload_may_name_its_provider() -> None:
    assert decision("gh run view 1 --job $J --log", provider="claude") == "allow"


@run_by_zsh
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh run list --commit $(git rev-parse HEAD)", id="a command substitution"),
        pytest.param("gh run list --commit `git rev-parse HEAD`", id="a backtick substitution"),
        pytest.param("gh run view 1 --job ${=J} --log", id="${=name} splits words"),
        pytest.param("gh run view 1 --job $=J --log", id="$=name splits words"),
        pytest.param("gh run view 1 --job ${~J} --log", id="${~name} globs the value"),
        pytest.param("gh run view 1 --job $~J --log", id="$~name globs the value"),
        pytest.param("gh run view 1 --job ${(s: :)J} --log", id="a split flag"),
        pytest.param("gh run view 1 --job ${(@)J} --log", id="the @ flag"),
        pytest.param("gh run view 1 --job ${J[1]} --log", id="a braced subscript"),
        pytest.param("gh run view 1 --job $J[1] --log", id="a subscript"),
        pytest.param("gh run view 1 --job ${J[@]} --log", id="an array expansion"),
        pytest.param("gh run view 1 --job ${J[*]} --log", id="a starred array expansion"),
        pytest.param("gh run view 1 --job ${J:-x y} --log", id="a default word"),
        pytest.param("gh run view 1 --job ${J#x} --log", id="a stripped prefix"),
        pytest.param("gh run view 1 --job ${#J} --log", id="a length"),
        pytest.param("gh run view 1 --job ${!J} --log", id="an indirection"),
        pytest.param("gh run view 1 --job $@ --log", id="all positional parameters"),
        pytest.param("gh run view 1 --job $* --log", id="all positional parameters as one"),
        pytest.param("gh run view 1 --job $1 --log", id="a positional parameter"),
        pytest.param("gh run view 1 --job $argv --log", id="the positional parameter array"),
        pytest.param("gh run view 1 --job $path --log", id="the path array"),
        pytest.param("gh run view 1 --job $pipestatus --log", id="the pipestatus array"),
        pytest.param("gh run view 1 --job $commands --log", id="an associative array"),
        pytest.param("gh run view 1 --job $J* --log", id="a glob after the variable"),
        pytest.param("gh run view 1 --job $J{a,b} --log", id="a brace expansion after the variable"),
        pytest.param("gh run view 1 --job ~$J --log", id="a tilde before the variable"),
        pytest.param("gh api $J", id="a call that is not listed once the word vanishes"),
        pytest.param("gh api $J $K", id="two words that may vanish"),
    ],
)
def test_forms_zsh_does_not_run_as_one_word_still_ask(command: str) -> None:
    assert decision(command) == "ask"


@run_by_zsh
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("a=(x y); gh run view 1 --job $a --log", id="an array assigned in the command"),
        pytest.param("a[2]=x; gh run view 1 --job $a --log", id="an element assigned in the command"),
        pytest.param("typeset -a a; gh run view 1 --job $a --log", id="an array declared in the command"),
        pytest.param("declare -A a; gh run view 1 --job $a --log", id="an association declared in the command"),
        pytest.param("read -rA a; gh run view 1 --job $a --log", id="an array read in the command"),
        pytest.param("set -A a x y; gh run view 1 --job $a --log", id="an array set in the command"),
        pytest.param("setopt sh_word_split; gh run view 1 --job $J --log", id="a changed option"),
        pytest.param("setopt glob_subst && gh run view 1 --job $J --log", id="a glob_subst option"),
        pytest.param("unsetopt nomatch; gh run view 1 --job $J --log", id="an unset option"),
        pytest.param("emulate sh; gh run view 1 --job $J --log", id="another emulation"),
        pytest.param("$SETUP; gh run view 1 --job $J --log", id="a variable as the program"),
        pytest.param("bash -c 'gh run view 1 --job $J --log'", id="a script another shell runs"),
        pytest.param("sh -c 'gh run view 1 --job $J --log'", id="a script sh runs"),
    ],
)
def test_a_command_that_may_change_how_zsh_expands_still_asks(command: str) -> None:
    assert decision(command) == "ask"


@run_by_zsh
def test_a_word_that_vanishes_when_empty_is_judged_without_it() -> None:
    assert decision("gh pr view $J $K --json state") == "allow"
    assert decision("gh api $J") == "ask"
    assert decision("gh api $J $K") == "ask"


@pytest.mark.parametrize("command", ["gh run view 1 --job $=J --log", "gh run view 1 --job $~J --log"])
def test_a_dollar_before_a_zsh_modifier_asks_whatever_the_shell(command: str) -> None:
    assert decision(command) == "ask"
