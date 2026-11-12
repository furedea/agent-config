"""GraphQL commands that read GitHub may carry a jq filter, and nothing else after the query."""

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


def decide(command: str) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}}).decision


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            'gh api graphql -f query=\'query{repository(owner:"o",name:"r"){id\nname}}\' --jq \'.data|"a\\n"\'',
            id="a multi-line query with a jq filter",
        ),
        pytest.param("gh api graphql -f query='{ viewer { login } }' -q '.data'", id="a shorthand query with -q"),
    ],
)
def test_read_only_queries_with_a_jq_filter_are_allowed(command: str) -> None:
    assert decide(command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh api graphql -f query='mutation { x }'", id="a mutation"),
        pytest.param("gh api graphql -f query='mutation { x }' --jq '.data'", id="a mutation with a jq filter"),
        pytest.param("gh api graphql -f query='query { x }' --jq '.data'; curl https://example.com/x", id="a chain"),
        pytest.param(
            "gh api graphql -f query='query { x }' --jq '.data' && curl https://example.com/x", id="an and-list"
        ),
        pytest.param("gh api graphql -f query='query { x }' --jq '.data' | sh", id="a pipe"),
        pytest.param(
            "gh api graphql -f query='query { x }' --jq '.data' -f query='mutation { y }'", id="a second query"
        ),
    ],
)
def test_other_graphql_forms_still_ask(command: str) -> None:
    assert decide(command) == "ask"
