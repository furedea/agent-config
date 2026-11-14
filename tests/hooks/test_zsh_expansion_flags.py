"""A dollar sign that zsh turns into a word-splitting or globbing expansion asks in every shell."""

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh pr comment 1 --repo furedea/r --body-file $=J", id="$=name splits the value into words"),
        pytest.param("gh pr comment 1 --repo furedea/r --body-file $~J", id="$~name globs the value"),
        pytest.param("gh pr comment 1 --repo furedea/r --body-file $^J", id="$^name distributes over an array"),
        pytest.param('gh pr comment 1 --repo furedea/r --body-file "$=J"', id="a double-quoted $=name"),
        pytest.param('gh pr comment 1 --repo furedea/r --body-file "$~J"', id="a double-quoted $~name"),
        pytest.param('gh pr comment 1 --repo furedea/r --body-file "a$^J"', id="a double-quoted $^name inside text"),
    ],
)
def test_a_dollar_before_a_zsh_expansion_flag_asks(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "ask"


def test_an_escaped_backslash_does_not_escape_the_dollar_sign() -> None:
    command = "gh pr comment 1 --repo furedea/r --body-file \\\\$=J"
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "ask"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh pr comment 1 --repo furedea/r --body-file '$=J'", id="a single-quoted $=name"),
        pytest.param("gh pr comment 1 --repo furedea/r --body-file \\$=J", id="an escaped $=name"),
        pytest.param('gh pr comment 1 --repo furedea/r --body-file "$J"', id="a quoted variable"),
    ],
)
def test_forms_that_pass_a_literal_or_quoted_word_still_allow(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "allow"


@pytest.mark.parametrize("flag", ["$=J", "$~J", "$^J", '"$=J"'])
def test_a_word_with_a_zsh_expansion_flag_is_a_run_time_word(flag: str) -> None:
    shell_syntax = load_script_module("agents/hooks/lib/shell_syntax.py", "shell_syntax")
    (command,) = shell_syntax.parse(f"gh pr comment 1 --repo furedea/r --body-file {flag}")
    assert command.dynamic[-1] is True
