"""Where the shell is zsh, only an unquoted TMPDIR, HOME, PWD, or USER is one word (ADR-0022)."""

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
        pytest.param("gh pr edit 438 --body-file $TMPDIR/body.md", id="TMPDIR"),
        pytest.param("gh pr edit 438 --body-file ${TMPDIR}/body.md", id="a braced TMPDIR"),
        pytest.param("gh pr edit 438 --body-file $HOME/body.md", id="HOME"),
        pytest.param("gh pr edit 438 --body-file $PWD/body.md", id="PWD"),
        pytest.param("gh run view 1 --job $USER --log", id="USER"),
        pytest.param("gh pr edit 438 --body-file $TMPDIR/body.md | head -5", id="a pipe after the call"),
        pytest.param("gh pr edit 438 --body-file $TMPDIR/body.md 2>&1 && echo done", id="redirects and && after"),
        pytest.param("export X=$Y; gh pr edit 438 --body-file $TMPDIR/body.md", id="an unrelated export before"),
        pytest.param('gh pr edit 438 --body-file "$TMPDIR/body.md"', id="a quoted expansion beside it"),
        pytest.param('gh run view 1 --job "$J" --log', id="a quoted variable, unchanged"),
        pytest.param("gh pr view $USER --json state", id="a vanishing word whose absence is still listed"),
    ],
)
def test_an_unquoted_environment_variable_is_judged_as_one_word(command: str) -> None:
    assert decision(command) == "allow"


@run_by_zsh
@pytest.mark.parametrize(
    "command",
    [
        pytest.param(RUN, id="a name outside the list"),
        pytest.param("J=42; gh run view 1 --job $J --log", id="an assigned name outside the list"),
        pytest.param("gh run view 1 --job $path --log", id="the path array"),
        pytest.param("gh run view 1 --job $argv --log", id="the positional parameter array"),
        pytest.param("gh run view 1 --job $commands --log", id="an associative array"),
        pytest.param("gh run view 1 --job $TMP --log", id="a name that only starts like a listed one"),
        pytest.param("gh run view 1 --job $1 --log", id="a positional parameter"),
        pytest.param("gh run view 1 --job $@ --log", id="all positional parameters"),
        pytest.param("gh run list --commit $(git rev-parse HEAD)", id="a command substitution"),
        pytest.param("gh api $TMPDIR", id="a word that may vanish into a call that is not listed"),
        pytest.param("gh api $TMPDIR $HOME", id="two words that may vanish"),
    ],
)
def test_any_other_unquoted_variable_still_asks(command: str) -> None:
    assert decision(command) == "ask"


@run_by_zsh
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("TMPDIR=(a b); gh pr edit 438 --body-file $TMPDIR/body.md", id="an array assignment"),
        pytest.param("TMPDIR=/x; gh pr edit 438 --body-file $TMPDIR/body.md", id="a plain assignment"),
        pytest.param("TMPDIR+=/x; gh pr edit 438 --body-file $TMPDIR/body.md", id="an append"),
        pytest.param("TMPDIR[2]=x; gh pr edit 438 --body-file $TMPDIR/body.md", id="an element assignment"),
        pytest.param("typeset -a TMPDIR; gh pr edit 438 --body-file $TMPDIR/body.md", id="a typeset"),
        pytest.param("declare -A HOME; gh pr edit 438 --body-file $HOME/body.md", id="a declare"),
        pytest.param("local PWD; gh pr edit 438 --body-file $PWD/body.md", id="a local"),
        pytest.param("export -T T_ TMPDIR; gh pr edit 438 --body-file $TMPDIR/body.md", id="an export that ties"),
        pytest.param("readonly -a USER; gh run view 1 --job $USER --log", id="a readonly array"),
        pytest.param("read -rA TMPDIR; gh pr edit 438 --body-file $TMPDIR/body.md", id="a read into an array"),
        pytest.param("unset TMPDIR; gh pr edit 438 --body-file $TMPDIR/body.md", id="an unset"),
        pytest.param("zparseopts -a TMPDIR -x; gh pr edit 438 --body-file $TMPDIR/body.md", id="a zparseopts"),
        pytest.param("trap 'TMPDIR=(a b)' DEBUG; gh pr edit 438 --body-file $TMPDIR/body.md", id="a trap"),
        pytest.param("f() { TMPDIR=(a b); }; f; gh pr edit 438 --body-file $TMPDIR/body.md", id="a function"),
        pytest.param("eval 'TMPDIR=(a b)'; gh pr edit 438 --body-file $TMPDIR/body.md", id="an eval"),
        pytest.param("repeat 1 unset TMPDIR; gh pr edit 438 --body-file $TMPDIR/body.md", id="a repeat"),
        pytest.param("set -A TMP''DIR 1 --repo o/r; gh run view $TMPDIR --log", id="a quoted spelling of the name"),
        pytest.param('typeset -a TMP"DIR"; gh run view $TMPDIR --log', id="a double-quoted spelling of the name"),
        pytest.param("read -A TMP\\DIR <<< x; gh run view $TMPDIR --log", id="an escaped spelling of the name"),
        pytest.param("typeset -a TMP\\\nDIR; gh run view $TMPDIR --log", id="a spelling split by a line continuation"),
        pytest.param("echo TMPDIR; gh pr edit 438 --body-file $TMPDIR/body.md", id="the name as any other argument"),
        pytest.param("gh pr edit 438 --body-file ${TMPDIR:-/tmp}/body.md", id="a modifier"),
        pytest.param("gh pr edit 438 --body-file $TMPDIR/body.md --title TMPDIR", id="the name beside the call"),
    ],
)
def test_a_name_that_appears_beyond_its_expansions_asks(command: str) -> None:
    assert decision(command) == "ask"


@run_by_zsh
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh run view 1 --job ${=TMPDIR} --log", id="${=name} splits words"),
        pytest.param("gh run view 1 --job ${~TMPDIR} --log", id="${~name} globs the value"),
        pytest.param("gh run view 1 --job ${(s: :)TMPDIR} --log", id="a split flag"),
        pytest.param("gh run view 1 --job ${TMPDIR[1]} --log", id="a braced subscript"),
        pytest.param("gh run view 1 --job $TMPDIR[1] --log", id="a subscript"),
        pytest.param("gh run view 1 --job ${TMPDIR[@]} --log", id="an array expansion"),
        pytest.param("gh run view 1 --job ${#TMPDIR} --log", id="a length"),
        pytest.param("gh run view 1 --job ${!TMPDIR} --log", id="an indirection"),
        pytest.param("gh run view 1 --job $TMPDIR* --log", id="a glob after the variable"),
        pytest.param("gh run view 1 --job $TMPDIR{a,b} --log", id="a brace expansion after the variable"),
        pytest.param("gh run view 1 --job ~$TMPDIR --log", id="a tilde before the variable"),
        pytest.param("bash -c 'gh pr edit 438 --body-file $TMPDIR/body.md'", id="a script another shell runs"),
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
    assert decision("gh pr edit 438 --body-file $TMPDIR/body.md", provider=provider) == "ask"


@run_by_zsh
def test_a_claude_payload_may_name_its_provider() -> None:
    assert decision("gh pr edit 438 --body-file $TMPDIR/body.md", provider="claude") == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "gh run view 1 --job $=J --log",
        "gh run view 1 --job $~J --log",
        "gh run view 1 --job \\\\$=J --log",
        'set -- a --admin; gh run view 1 --job ~"$@" --log',
        'gh run view 1 --job ~/x"${A[@]}" --log',
    ],
)
def test_a_dollar_before_a_zsh_modifier_asks_whatever_the_shell(command: str) -> None:
    assert decision(command) == "ask"
