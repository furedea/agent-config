"""A `&&` list of gh or herdr calls, each optionally piped through read-only filters, is judged part by part."""

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


def decision(command: str) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}}).decision


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "herdr agent wait lane-a --until working && herdr agent wait lane-a --until done",
            id="a && list of Herdr waits",
        ),
        pytest.param("herdr agent read lane-a --lines 40 | head -20", id="a Herdr read through head"),
        pytest.param("gh api repos/o/r/pulls | jq '.' | head -3", id="GitHub reads through several filters"),
        pytest.param(
            "gh api repos/o/r/pulls && herdr agent read lane-a | wc -l", id="a && list holding a filtered pipeline"
        ),
        pytest.param(
            "gh api repos/o/r/pulls && gh api repos/o/r/issues && herdr agent read a", id="a three-part && list"
        ),
    ],
)
def test_and_lists_and_filtered_pipelines_of_literal_commands_pass(command: str) -> None:
    assert decision(command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh pr list && gh pr review 42 --approve | head", id="a forbidden pipeline after &&"),
        pytest.param("herdr agent read a && gh pr review 42 --approve", id="an unlisted form last in a && list"),
        pytest.param("gh pr review 42 --approve && herdr agent read a", id="an unlisted form first in a && list"),
        pytest.param("herdr agent read a; herdr agent read a", id="a ; list"),
        pytest.param("herdr agent read a || herdr agent read a", id="a || list"),
        pytest.param("herdr agent read a && herdr agent read a &", id="a background && list"),
        pytest.param("herdr agent read a && herdr agent read a > out.txt", id="a redirect in a && list"),
        pytest.param("herdr agent read a && X=1 herdr agent read a", id="an assignment in a && list"),
        pytest.param("herdr agent read a && (herdr agent read a)", id="a subshell in a && list"),
        pytest.param("herdr agent read a && herdr agent read $L", id="a variable in a && list"),
        pytest.param("herdr agent read a && herdr agent read $(echo a)", id="a substitution in a && list"),
        pytest.param("herdr agent read a && herdr agent read `echo a`", id="a backtick in a && list"),
        pytest.param("herdr agent read a && herdr agent read a*", id="a glob in a && list"),
        pytest.param("! herdr agent read a && herdr agent read a", id="a negated && list"),
        pytest.param("herdr agent read a && env herdr agent read a", id="a wrapper in a && list"),
        pytest.param("herdr agent read a | tee out.txt", id="a pipe into tee"),
        pytest.param("herdr agent read a | xargs echo", id="a pipe into xargs"),
        pytest.param("herdr agent read a | sh", id="a pipe into sh"),
        pytest.param("herdr agent read a | head --bogus", id="a filter with an unknown option"),
        pytest.param("herdr agent read a | jq 'map(.id)'", id="a jq program beyond the listed ones"),
        pytest.param("herdr agent read a | head > out.txt", id="a redirect after a filter"),
        pytest.param("gh api repos/o/r/pulls | herdr agent read a", id="a literal program as a filter"),
        pytest.param("echo a | herdr agent read a", id="a non-literal program heading a pipeline"),
        pytest.param("for n in 1 2; do herdr agent read a && herdr agent read a; done", id="a && list in a loop"),
    ],
)
def test_neighbouring_compound_forms_ask(command: str) -> None:
    assert decision(command) == "ask"
