"""A GraphQL document yields its operations and each operation's root fields, or refuses text it cannot place."""

import pytest
from tests.runtime import load_script_module

graphql = load_script_module("agents/hooks/lib/graphql_document.py", "graphql_document")
QUERY, MUTATION = graphql.OperationType.QUERY, graphql.OperationType.MUTATION


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        pytest.param("{ viewer { login } }", [(QUERY, ("viewer",))], id="a shorthand query"),
        pytest.param("query Q($n: Int = 3) @x { a(n: $n) { b } c }", [(QUERY, ("a", "c"))], id="a named query"),
        pytest.param(
            'mutation{a:resolveReviewThread(input:{threadId:"x"}){thread{isResolved}} '
            "b:unresolveReviewThread(input:{})}",
            [(MUTATION, ("resolveReviewThread", "unresolveReviewThread"))],
            id="aliased mutations",
        ),
        pytest.param(
            'mutation { add(body: "a } mutation { evil }") { id } }', [(MUTATION, ("add",))], id="braces in a string"
        ),
        pytest.param(
            'mutation { add(body: """a "" } b""") { id } }', [(MUTATION, ("add",))], id="braces in a block string"
        ),
        pytest.param("# mutation { evil }\n{ a }", [(QUERY, ("a",))], id="a comment"),
        pytest.param(
            "query { a } fragment F on Q { mutation } mutation M { b @skip(if: true) }",
            [(QUERY, ("a",)), (MUTATION, ("b",))],
            id="a fragment between operations",
        ),
    ],
)
def test_operations_and_their_root_fields_are_read(
    document: str, expected: list[tuple[object, tuple[str, ...]]]
) -> None:
    assert [(item.type, item.root_fields) for item in graphql.operations(document)] == expected


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("", id="no operation"),
        pytest.param("{ a", id="an unclosed selection"),
        pytest.param("{ a(x: [1) }", id="mismatched brackets"),
        pytest.param("mutation { ...F }", id="a root fragment spread"),
        pytest.param("mutation { a: }", id="an alias without a field"),
        pytest.param("extend type Q { a }", id="a type system definition"),
        pytest.param('{ a(s: "unterminated) }', id="an unterminated string"),
        pytest.param("{ a } ~", id="an unknown character"),
    ],
)
def test_text_the_reader_cannot_place_is_refused(document: str) -> None:
    with pytest.raises(graphql.GraphQLSyntaxError):
        graphql.operations(document)
