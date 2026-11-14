"""Precise command rules judge a static word the same whichever quoting writes it."""

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            'gh api repos/furedea/r/pulls/1/comments/2/replies -f body="Fixed."',
            id="double-quoted static reply bodies",
        ),
        pytest.param(
            "gh api repos/furedea/r/pulls/1/comments/2/replies -f body=Fixed\\.",
            id="backslash-escaped static reply bodies",
        ),
        pytest.param(
            'gh api repos/furedea/r/pulls/1/comments/2/replies -f body="it\'s great"',
            id="double-quoted reply bodies holding an apostrophe",
        ),
        pytest.param('gh run list --commit "$sha"', id="quoted run-time commits"),
        pytest.param(
            'gh api repos/furedea/r/pulls/1/comments/2/replies -f body="Fixed \\`x\\`."',
            id="double-quoted escaped backticks",
        ),
        pytest.param(
            'gh api repos/furedea/r/pulls/1/comments/2/replies -f body="Fixed \\$x."',
            id="double-quoted escaped dollars",
        ),
        pytest.param('gh api repos/furedea/r/pulls/1/comments/2/replies -f body="a\\"b"', id="double-quoted escapes"),
    ],
)
def test_static_words_match_precise_rules_by_value_not_quoting(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            'gh api repos/furedea/r/pulls/1/comments/2/replies -f body="Fixed $x."', id="double-quoted expansions"
        ),
        pytest.param(
            "x='1 -R other/r'; gh pr comment 1 --repo furedea/r --body-file $x", id="an assigned value that splits"
        ),
    ],
)
def test_words_that_expand_or_vary_at_run_time_still_ask(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "ask"
