"""Inspect literal text and pipeline structure for supplementary command policy."""

from collections.abc import Callable

import shell_syntax


def text_outside_single_quotes(source: str) -> str:
    """The source without its single-quoted strings, which no shell expands; $'...' stays, as it decodes escapes."""
    return _text_without_nodes(source, lambda node: node.get("Type") == "SglQuoted" and not node.get("Dollar"))


def text_outside_quotes(source: str) -> str:
    """The source without any quoted string, so only text the shell may expand as a glob, brace, or tilde remains.

    $'...' and $"..." keep their leading dollar sign, which marks them for review.
    """
    return _text_without_nodes(source, _is_plain_quoted)


def double_quoted_text(source: str) -> str:
    r"""The text of each double-quoted string, where only `$`, a backtick, `\`, and `!` stay special."""
    data = source.encode()
    return "".join(
        data[begin:end].decode()
        for begin, end in _outermost_spans(source, lambda node: node.get("Type") == "DblQuoted")
    )


def _is_plain_quoted(node: dict) -> bool:
    return node.get("Type") in {"SglQuoted", "DblQuoted"} and not node.get("Dollar")


def _text_without_nodes(source: str, selects: Callable[[dict], bool]) -> str:
    data = source.encode()
    kept, start = [], 0
    for begin, end in _outermost_spans(source, selects):
        kept.append(data[start:begin])
        start = end
    kept.append(data[start:])
    return b"".join(kept).decode()


def _outermost_spans(source: str, selects: Callable[[dict], bool]) -> list[tuple[int, int]]:
    spans = sorted(
        (node["Pos"]["Offset"], node["End"]["Offset"])
        for node in shell_syntax.nodes(shell_syntax.syntax_tree(source))
        if selects(node)
    )
    outermost: list[tuple[int, int]] = []
    for begin, end in spans:
        if outermost and begin < outermost[-1][1]:
            outermost[-1] = (outermost[-1][0], max(outermost[-1][1], end))
        else:
            outermost.append((begin, end))
    return outermost


def is_plain_pipeline(source: str) -> bool:
    """Accept only a single foreground pipeline of unwrapped simple calls."""
    statements = shell_syntax.syntax_tree(source).get("Stmts", [])
    if len(statements) != 1:
        return False
    return _plain_pipeline_statement(statements[0], source.encode())


def _plain_pipeline_statement(statement: dict, data: bytes) -> bool:
    if _has_statement_flag(statement):
        return False
    command = statement.get("Cmd", {})
    if command.get("Type") == "CallExpr":
        return not command.get("Assigns")
    if command.get("Type") != "BinaryCmd":
        return False
    offset = command["OpPos"]["Offset"]
    if data[offset : offset + 1] != b"|" or data[offset + 1 : offset + 2] in {b"|", b"&"}:
        return False
    return all(_plain_pipeline_statement(command[side], data) for side in ("X", "Y"))


def plain_and_list_shape(source: str) -> tuple[int, ...] | None:
    """The length of each pipeline in a foreground `&&` list of unwrapped simple calls; None for any other shape."""
    statements = shell_syntax.syntax_tree(source).get("Stmts", [])
    if len(statements) != 1:
        return None
    return _and_list_lengths(statements[0], source.encode())


def _and_list_lengths(statement: dict, data: bytes) -> tuple[int, ...] | None:
    if _has_statement_flag(statement):
        return None
    command = statement.get("Cmd", {})
    if command.get("Type") == "CallExpr":
        return None if command.get("Assigns") else (1,)
    if command.get("Type") != "BinaryCmd":
        return None
    offset = command["OpPos"]["Offset"]
    if data[offset : offset + 2] == b"&&":
        left, right = (_and_list_lengths(command[side], data) for side in ("X", "Y"))
        return None if left is None or right is None else (*left, *right)
    if _plain_pipeline_statement(statement, data):
        return (_pipeline_length(statement),)
    return None


def _pipeline_length(statement: dict) -> int:
    command = statement["Cmd"]
    if command.get("Type") == "CallExpr":
        return 1
    return sum(_pipeline_length(command[side]) for side in ("X", "Y"))


def _has_statement_flag(statement: dict) -> bool:
    return any(statement.get(flag) for flag in ("Background", "Coprocess", "Negated", "Disown", "Redirs"))
