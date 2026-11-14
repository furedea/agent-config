"""Read which operations a GraphQL document defines and which root fields each mutation selects.

Only what the gh guard needs is parsed: operation types, and the root fields of mutations. Any text
this reader does not understand raises GraphQLSyntaxError, so the guard asks instead of guessing.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

TOKEN = re.compile(
    r"(?P<ignored>[\s,﻿]+|#[^\n\r]*)"
    r'|(?P<block>"""(?:\\"""|(?!""").)*""")'
    r'|(?P<string>"(?:\\.|[^"\\\n\r])*")'
    r"|(?P<spread>\.\.\.)"
    r"|(?P<name>[_A-Za-z][_0-9A-Za-z]*)"
    r"|(?P<number>-?[0-9][0-9.eE+-]*)"
    r"|(?P<punctuator>[!$&()\:=@\[\]{|}])",
    re.DOTALL,
)
OPENING = {"(": ")", "[": "]", "{": "}"}


class GraphQLSyntaxError(ValueError):
    """The document holds text this reader cannot place, so its effect is unknown."""


class OperationType(StrEnum):
    """The root type an operation runs against."""

    QUERY = "query"
    MUTATION = "mutation"
    SUBSCRIPTION = "subscription"


@dataclass(frozen=True, slots=True)
class Operation:
    """One executable operation and the root fields it selects."""

    type: OperationType
    root_fields: tuple[str, ...]


def operations(document: str) -> tuple[Operation, ...]:
    """Every operation the document defines; fragments are skipped, since only operations run."""
    tokens = _tokens(document)
    found: list[Operation] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "{":
            fields, index = _root_fields(tokens, index)
            found.append(Operation(OperationType.QUERY, fields))
        elif token in OperationType.__members__.values():
            index = _skip_header(tokens, index + 1)
            fields, index = _root_fields(tokens, index)
            found.append(Operation(OperationType(token), fields))
        elif token == "fragment":
            index = _skip_until_selection(tokens, index + 1)
            index = _skip_balanced(tokens, index)
        else:
            raise GraphQLSyntaxError(f"unexpected token {token!r}")
    if not found:
        raise GraphQLSyntaxError("no operation")
    return tuple(found)


def _tokens(document: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(document):
        match = TOKEN.match(document, position)
        if match is None:
            raise GraphQLSyntaxError(f"unreadable text at {position}")
        position = match.end()
        if match.lastgroup != "ignored":
            tokens.append(match.group())
    return tokens


def _skip_header(tokens: list[str], index: int) -> int:
    """Skip an operation's name, variable definitions, and directives up to its selection set."""
    if index < len(tokens) and _is_name(tokens[index]):
        index += 1
    return _skip_until_selection(tokens, index)


def _skip_until_selection(tokens: list[str], index: int) -> int:
    while index < len(tokens) and tokens[index] != "{":
        index = _skip_balanced(tokens, index) if tokens[index] in OPENING else index + 1
    if index >= len(tokens):
        raise GraphQLSyntaxError("missing selection set")
    return index


def _root_fields(tokens: list[str], index: int) -> tuple[tuple[str, ...], int]:
    """The field names (not aliases) selected directly in the selection set opening at index."""
    fields: list[str] = []
    index += 1
    while index < len(tokens) and tokens[index] != "}":
        if tokens[index] == "...":
            raise GraphQLSyntaxError("fragment at the root of an operation")
        if not _is_name(tokens[index]):
            raise GraphQLSyntaxError(f"unexpected token {tokens[index]!r}")
        name, index = _field_name(tokens, index)
        fields.append(name)
        index = _skip_field_tail(tokens, index)
    if index >= len(tokens):
        raise GraphQLSyntaxError("unclosed selection set")
    return tuple(fields), index + 1


def _field_name(tokens: list[str], index: int) -> tuple[str, int]:
    """The field a selection names, past its alias if it has one, and the index after it."""
    if index + 1 >= len(tokens) or tokens[index + 1] != ":":
        return tokens[index], index + 1
    if index + 2 >= len(tokens) or not _is_name(tokens[index + 2]):
        raise GraphQLSyntaxError("alias without a field")
    return tokens[index + 2], index + 3


def _skip_field_tail(tokens: list[str], index: int) -> int:
    """Skip a field's arguments, directives, and sub-selection."""
    if index < len(tokens) and tokens[index] == "(":
        index = _skip_balanced(tokens, index)
    while index < len(tokens) and tokens[index] == "@":
        index += 2
        if index < len(tokens) and tokens[index] == "(":
            index = _skip_balanced(tokens, index)
    if index < len(tokens) and tokens[index] == "{":
        index = _skip_balanced(tokens, index)
    return index


def _skip_balanced(tokens: list[str], index: int) -> int:
    """The index after the bracket that closes the one at index."""
    stack = [OPENING[tokens[index]]]
    index += 1
    while index < len(tokens) and stack:
        token = tokens[index]
        if token in OPENING:
            stack.append(OPENING[token])
        elif token in OPENING.values() and token != stack.pop():
            raise GraphQLSyntaxError("mismatched brackets")
        index += 1
    if stack:
        raise GraphQLSyntaxError("unclosed bracket")
    return index


def _is_name(token: str) -> bool:
    return bool(re.fullmatch(r"[_A-Za-z][_0-9A-Za-z]*", token))
