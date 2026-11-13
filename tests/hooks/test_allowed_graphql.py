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
        pytest.param("gh api graphql -f query='query { viewer { login } }'", id="a query without a filter"),
        pytest.param('gh api graphql -f query="query { viewer { login } }"', id="a double-quoted query"),
        pytest.param(
            "gh api graphql -f query='query($o:String!){repository(owner:$o,name:\"r\"){id}}' -f o=furedea",
            id="a -f variable",
        ),
        pytest.param(
            "gh api graphql -f query='query($n:Int!){x(n:$n){id}}' -F n=12 -f o=furedea --jq '.data'",
            id="-F number variables and a -f variable with a filter",
        ),
        pytest.param(
            "gh api graphql -f query='query { a } # x' -F ok=true",
            id="a -F boolean variable",
        ),
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


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh api graphql -f query='query { x } mutation { y }'", id="a mutation after a query"),
        pytest.param("gh api graphql -f query='query { x }' -f note=mutation", id="the keyword in a variable"),
        pytest.param("gh api graphql -f query='query { x } MUTATION { y }'", id="an upper-case keyword"),
        pytest.param("gh api graphql -f query='query { x } Mutation { y }'", id="a capitalized keyword"),
        pytest.param("gh api graphql -f query='query { x }' --jq '.mutation'", id="the keyword in a filter"),
        pytest.param("gh api graphql -f query='query { x }' -F n=@secret.txt", id="a -F variable that reads a file"),
        pytest.param("gh api graphql -f query='query { x }' -F n=abc", id="a -F variable that is not a literal"),
        pytest.param("gh api graphql -f query='query { x }' -f n=@secret.txt", id="a -f value with @"),
        pytest.param("gh api graphql -f query='query { x }' -f n='a b'", id="a quoted variable value"),
        pytest.param("gh api graphql -f query='query { x }' -f operationName=y", id="an operation name"),
        pytest.param("gh api graphql -f query='query { x }' -F query=@q.graphql", id="a query from a file"),
        pytest.param("gh api graphql -F query=@q.graphql", id="only a query file"),
        pytest.param("gh api graphql -f query='query { x }' --input body.json", id="a request body from a file"),
        pytest.param("gh api graphql -f query='query { x }' -X POST", id="an explicit method"),
        pytest.param("gh api graphql -f query='fragment F on User { id }'", id="a document not starting as a query"),
        pytest.param("gh api graphql -f query=query", id="an unquoted query"),
        pytest.param('gh api graphql -f query="query { $x }"', id="an expansion in a double-quoted query"),
    ],
)
def test_graphql_forms_that_could_write_or_read_files_ask(command: str) -> None:
    assert decide(command) == "ask"
