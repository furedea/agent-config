"""Precise command rules judge a static word the same whichever quoting writes it."""

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            'gh api repos/o/r/pulls/1/comments/2/replies -f body="Fixed."',
            id="double-quoted static reply bodies",
        ),
        pytest.param(
            "gh api repos/o/r/pulls/1/comments/2/replies -f body=Fixed\\.",
            id="backslash-escaped static reply bodies",
        ),
        pytest.param(
            'gh api repos/o/r/pulls/1/comments/2/replies -f body="it\'s great"',
            id="double-quoted reply bodies holding an apostrophe",
        ),
        pytest.param('gh run list --commit "$sha"', id="quoted run-time commits"),
    ],
)
def test_static_words_match_precise_rules_by_value_not_quoting(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh run list --commit $sha", id="unquoted run-time commits"),
        pytest.param("sha=0123456789abcdef0123456789abcdef01234567; gh run list --commit $sha", id="assigned commits"),
        pytest.param("gh run list --commit $(git rev-parse HEAD)", id="commits from command substitution"),
        pytest.param('gh api repos/o/r/pulls/1/comments/2/replies -f body="Fixed `x`."', id="double-quoted backticks"),
        pytest.param('gh api repos/o/r/pulls/1/comments/2/replies -f body="Fixed $x."', id="double-quoted expansions"),
        pytest.param(
            'gh api repos/o/r/pulls/1/comments/2/replies -f body="Fixed!"', id="double-quoted history expansion"
        ),
        pytest.param('gh api repos/o/r/pulls/1/comments/2/replies -f body="a\\"b"', id="double-quoted escapes"),
    ],
)
def test_words_that_expand_or_vary_at_run_time_still_ask(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "ask"
