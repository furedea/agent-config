"""Where the shell is zsh, an unquoted variable is one word only if the text proves it (ADR-0022)."""

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")

RUN = "gh run view 1 --job $J --log"


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
        pytest.param("J=42853069590; gh run view 1 --job $J --log", id="a name assigned before"),
        pytest.param("J=42853069590; gh run view 1 --job ${J} --log", id="a braced name assigned before"),
        pytest.param("J='42 853'; gh run view 1 --job $J --log", id="a quoted static value"),
        pytest.param('J="$X"; gh run view 1 --job $J --log', id="a quoted expansion as the value"),
        pytest.param("J=$(echo 42); gh run view 1 --job $J --log", id="a command substitution as the value"),
        pytest.param("J=1; K=2; gh pr view $J $K --json state", id="two names assigned before"),
        pytest.param("J=1 K=2; gh pr view $J $K --json state", id="two names in one assignment statement"),
        pytest.param("J=1; J+=2; gh run view 1 --job $J --log", id="an appended scalar"),
        pytest.param("export J=42; gh run view 1 --job $J --log", id="a name exported with its value"),
        pytest.param("J=42; gh run view 1 --job $J --log | head -20", id="a pipe after the call"),
        pytest.param("J=42; gh run view 1 --job $J --log 2>&1 && echo done", id="redirects and && after the call"),
        pytest.param("J=42; echo start | gh run view 1 --job $J --log", id="the call at the end of a pipe"),
        pytest.param("gh pr edit 438 --body-file $TMPDIR/body.md", id="TMPDIR with no assignment"),
        pytest.param("gh pr edit 438 --body-file ${TMPDIR}/body.md", id="a braced TMPDIR"),
        pytest.param("gh pr edit 438 --body-file $HOME/body.md", id="HOME"),
        pytest.param("gh pr edit 438 --body-file $PWD/body.md", id="PWD"),
        pytest.param("gh run view 1 --job $USER --log", id="USER"),
        pytest.param('gh run view 1 --job "$J" --log', id="a quoted variable, unchanged"),
        pytest.param('export X=$Y; gh run view 1 --job "$J" --log', id="an export before a quoted call"),
        pytest.param("J=1; gh pr view $J --json state", id="a vanishing word whose absence is still listed"),
    ],
)
def test_a_variable_the_text_proves_to_be_one_word_is_judged_as_one_word(command: str) -> None:
    assert decision(command) == "allow"


@run_by_zsh
@pytest.mark.parametrize(
    "command",
    [
        pytest.param(RUN, id="a name never assigned"),
        pytest.param("gh run view 1 --job $path --log", id="the path array"),
        pytest.param("gh run view 1 --job $argv --log", id="the positional parameter array"),
        pytest.param("gh run view 1 --job $commands --log", id="an associative array"),
        pytest.param("gh run view 1 --job $module_path --log", id="the module_path array"),
        pytest.param("gh run list --commit $(git rev-parse HEAD)", id="a command substitution"),
        pytest.param("gh run view 1 --job $1 --log", id="a positional parameter"),
        pytest.param("gh run view 1 --job $@ --log", id="all positional parameters"),
        pytest.param("gh run view 1 --job $J --log; J=1", id="an assignment after the use"),
        pytest.param("J=1 gh run view 1 --job $J --log", id="an assignment only in the call's environment"),
        pytest.param("gh api $TMPDIR", id="a word that may vanish into a call that is not listed"),
        pytest.param("J=1; gh api $J $K", id="two words that may vanish"),
    ],
)
def test_a_variable_the_text_does_not_prove_to_be_one_word_still_asks(command: str) -> None:
    assert decision(command) == "ask"


@run_by_zsh
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("J=(x y); gh run view 1 --job $J --log", id="an array assignment"),
        pytest.param("J=1; J=(x y); gh run view 1 --job $J --log", id="a later array assignment"),
        pytest.param("J=1; J[2]=x; gh run view 1 --job $J --log", id="an element assignment"),
        pytest.param("J=1; typeset -a J; gh run view 1 --job $J --log", id="a typeset"),
        pytest.param("J=1; declare -A J; gh run view 1 --job $J --log", id="a declare"),
        pytest.param("J=1; local J; gh run view 1 --job $J --log", id="a local"),
        pytest.param("J=1; export -T J_ J; gh run view 1 --job $J --log", id="an export that ties arrays"),
        pytest.param("J=1; readonly -a J; gh run view 1 --job $J --log", id="a readonly array"),
        pytest.param("J=1; read -rA J; gh run view 1 --job $J --log", id="a read into an array"),
        pytest.param("J=1; unset J; gh run view 1 --job $J --log", id="an unset"),
        pytest.param("J=1; zparseopts -a J -x; gh run view 1 --job $J --log", id="a zparseopts"),
        pytest.param("J=1; f() { J=(a b); }; f; gh run view 1 --job $J --log", id="a function definition"),
        pytest.param("J=1; (J=(a b)); gh run view 1 --job $J --log", id="a subshell"),
        pytest.param("J=1; { J=(a b); }; gh run view 1 --job $J --log", id="a block"),
        pytest.param("J=1; if true; then J=(a b); fi; gh run view 1 --job $J --log", id="a control construct"),
        pytest.param("J=1; for J in a b; do :; done; gh run view 1 --job $J --log", id="a loop"),
        pytest.param("J=1; setopt sh_word_split; gh run view 1 --job $J --log", id="a changed option"),
        pytest.param("J=1; unsetopt nomatch; gh run view 1 --job $J --log", id="an unset option"),
        pytest.param("J=1; emulate sh; gh run view 1 --job $J --log", id="another emulation"),
        pytest.param("J=1; trap 'setopt sh_word_split' DEBUG; gh run view 1 --job $J --log", id="a trap"),
        pytest.param("J=1; - setopt sh_word_split; gh run view 1 --job $J --log", id="a dash prefix"),
        pytest.param("J=1; eval 'J=(a b)'; gh run view 1 --job $J --log", id="an eval"),
        pytest.param("setopt sh_word_split; gh pr edit 438 --body-file $TMPDIR/body.md", id="an option before TMPDIR"),
        pytest.param("cd /tmp; gh pr edit 438 --body-file $TMPDIR/body.md", id="another command before TMPDIR"),
        pytest.param("true || J=1; gh run view 1 --job $J --log", id="an assignment that may not run"),
        pytest.param("false && J=1; gh run view 1 --job $J --log", id="an assignment behind &&"),
        pytest.param("J=1 && gh run view 1 --job $J --log", id="the call behind &&"),
        pytest.param("J=1 || gh run view 1 --job $J --log", id="the call behind ||"),
        pytest.param("J=1 & gh run view 1 --job $J --log", id="a background assignment"),
        pytest.param("J=1 | cat; gh run view 1 --job $J --log", id="an assignment in a pipe"),
        pytest.param("true && gh run view 1 --job $TMPDIR --log", id="a call behind another command"),
        pytest.param("if J=1; then gh run view 1 --job $J --log; fi", id="a call inside a control construct"),
        pytest.param("f() { J=1; gh run view 1 --job $J --log; }; f", id="a call inside a function"),
        pytest.param("bash -c 'J=1; gh run view 1 --job $J --log'", id="a script another shell runs"),
        pytest.param("sh -c 'J=1; gh run view 1 --job $J --log'", id="a script sh runs"),
    ],
)
def test_an_assignment_that_may_be_retargeted_or_skipped_does_not_count(command: str) -> None:
    assert decision(command) == "ask"


@run_by_zsh
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("J=1; gh run view 1 --job ${=J} --log", id="${=name} splits words"),
        pytest.param("J=1; gh run view 1 --job $=J --log", id="$=name splits words"),
        pytest.param("J=1; gh run view 1 --job ${~J} --log", id="${~name} globs the value"),
        pytest.param("J=1; gh run view 1 --job $~J --log", id="$~name globs the value"),
        pytest.param("J=1; gh run view 1 --job ${(s: :)J} --log", id="a split flag"),
        pytest.param("J=1; gh run view 1 --job ${J[1]} --log", id="a braced subscript"),
        pytest.param("J=1; gh run view 1 --job $J[1] --log", id="a subscript"),
        pytest.param("J=1; gh run view 1 --job ${J[@]} --log", id="an array expansion"),
        pytest.param("J=1; gh run view 1 --job ${J:-x y} --log", id="a default word"),
        pytest.param("J=1; gh run view 1 --job ${J#x} --log", id="a stripped prefix"),
        pytest.param("J=1; gh run view 1 --job ${#J} --log", id="a length"),
        pytest.param("J=1; gh run view 1 --job ${!J} --log", id="an indirection"),
        pytest.param("J=1; gh run view 1 --job $J* --log", id="a glob after the variable"),
        pytest.param("J=1; gh run view 1 --job $J{a,b} --log", id="a brace expansion after the variable"),
        pytest.param("J=1; gh run view 1 --job ~$J --log", id="a tilde before the variable"),
        pytest.param("gh run view 1 --job ${TMPDIR:-/tmp} --log", id="a modifier on TMPDIR"),
        pytest.param("gh run view 1 --job $TMPDIR[1] --log", id="a subscript on TMPDIR"),
    ],
)
def test_forms_zsh_does_not_run_as_one_word_still_ask(command: str) -> None:
    assert decision(command) == "ask"


@pytest.mark.parametrize(
    "environment",
    [
        pytest.param({"SHELL": "/bin/bash"}, id="bash"),
        pytest.param({"SHELL": "/bin/zsh", "CLAUDE_CODE_SHELL": "/bin/bash"}, id="a shell chosen for Claude Code"),
        pytest.param({}, id="an unknown shell"),
    ],
)
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("J=1; gh run view 1 --job $J --log", id="an assigned name"),
        pytest.param("gh pr edit 438 --body-file $TMPDIR/body.md", id="TMPDIR"),
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
    assert decision("J=1; gh run view 1 --job $J --log", provider=provider) == "ask"


@run_by_zsh
def test_a_claude_payload_may_name_its_provider() -> None:
    assert decision("J=1; gh run view 1 --job $J --log", provider="claude") == "allow"


@pytest.mark.parametrize("command", ["gh run view 1 --job $=J --log", "gh run view 1 --job $~J --log"])
def test_a_dollar_before_a_zsh_modifier_asks_whatever_the_shell(command: str) -> None:
    assert decision(command) == "ask"
