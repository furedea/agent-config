"""Inspect literal text and pipeline structure for supplementary command policy."""

from collections.abc import Callable

import shell_syntax


def text_outside_single_quotes(source: str) -> str:
    """The source without its single-quoted strings, which no shell expands; $'...' stays, as it decodes escapes."""
    return text_without_nodes(source, lambda node: node.get("Type") == "SglQuoted" and not node.get("Dollar"))


def text_outside_quotes(source: str) -> str:
    """The source without any quoted string, so only text the shell may expand as a glob, brace, or tilde remains.

    $'...' and $"..." keep their leading dollar sign, which marks them for review.
    """
    return text_without_nodes(source, is_plain_quoted)


def double_quoted_text(source: str) -> str:
    """The text of each double-quoted string, where only `$`, a backtick, `\\`, and `!` stay special."""
    data = source.encode()
    return "".join(
        data[begin:end].decode()
        for begin, end in outermost_spans(source, lambda node: node.get("Type") == "DblQuoted")
    )


def is_plain_quoted(node: dict) -> bool:
    return node.get("Type") in {"SglQuoted", "DblQuoted"} and not node.get("Dollar")


def text_without_nodes(source: str, selects: Callable[[dict], bool]) -> str:
    data = source.encode()
    kept, start = [], 0
    for begin, end in outermost_spans(source, selects):
        kept.append(data[start:begin])
        start = end
    kept.append(data[start:])
    return b"".join(kept).decode()


def outermost_spans(source: str, selects: Callable[[dict], bool]) -> list[tuple[int, int]]:
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
    return plain_pipeline_statement(statements[0], source.encode())


def plain_pipeline_statement(statement: dict, data: bytes) -> bool:
    flags = ("Background", "Coprocess", "Negated", "Disown", "Redirs")
    if any(statement.get(flag) for flag in flags):
        return False
    command = statement.get("Cmd", {})
    if command.get("Type") == "CallExpr":
        return not command.get("Assigns")
    if command.get("Type") != "BinaryCmd":
        return False
    offset = command["OpPos"]["Offset"]
    if data[offset : offset + 1] != b"|" or data[offset + 1 : offset + 2] in {b"|", b"&"}:
        return False
    return all(plain_pipeline_statement(command[side], data) for side in ("X", "Y"))
