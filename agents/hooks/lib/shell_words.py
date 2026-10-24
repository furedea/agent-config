"""Decode shfmt word nodes into literal values, or into source text the shell computes at run time."""

from collections.abc import Iterator
import os
import re
import shlex
from typing import Literal


# Every command inside a substitution, clause, or function body is a CallExpr that parse judges on
# its own, so a body is judged where it is defined and a call by its own name; the substituted word
# itself is only known at run time.
SUBSTITUTIONS = frozenset({"CmdSubst", "ProcSubst", "ArithmExp"})
# A ParamExp other than the home directory makes its word a run-time word; Word is an operand inside it.
WORD_PARTS = frozenset({None, "Lit", "SglQuoted", "DblQuoted", "ParamExp", "Word"}) | SUBSTITUTIONS
QUOTED_PARTS = frozenset({"SglQuoted", "DblQuoted"})
HOME_PARAMETER = "HOME"
PARAMETER_MODIFIERS = ("Excl", "Length", "Width", "Index", "Slice", "Repl", "Exp")
# All positional parameters, any single one (a digit), and every array element ([@] or [*]) can
# become any number of words, options included, even inside double quotes.
SPREADING = frozenset({"@", "*"})
# Parts that the shell splits into words, or expands into several, when they stand outside quotes.
SPLIT_PARTS = frozenset({"ParamExp", "CmdSubst", "ProcSubst", "ArithmExp"})
# A bracket opens a glob only when a closing bracket follows, so the test command `[` stays literal.
GLOB = re.compile(r"(?<!\\)[*?]|(?<!\\)\[.+\]")
# Brace expansion can pair braces across quoted parts, so any unquoted brace counts.
BRACES = frozenset("{}")
LINE_CONTINUATION = "\\\n"


class UnsupportedSyntax(ValueError):
    """The command cannot be statically inspected by this supplementary guard."""

    def __init__(
        self,
        message: str,
        kind: Literal["heredoc", "expansion", "dollar-quote", "wrapper", "parse-failure"] = "parse-failure",
    ) -> None:
        super().__init__(message)
        self.kind = kind


def source_text(node: dict, source: bytes) -> str:
    """Use byte offsets so non-ASCII input cannot shift command boundaries."""
    return source[node["Pos"]["Offset"] : node["End"]["Offset"]].decode()


def literal_word(word: dict, source: bytes) -> tuple[str, bool]:
    """Decode a word the tree proves static, or return its source text flagged as dynamic.

    Only substitutions that run code (command, process, and arithmetic substitution) and
    dollar-quoted or heredoc forms are refused outright; a glob or a parameter other than the
    home directory is reported to the caller, which decides whether the program can take it.
    """
    dynamic = False
    for part in word_nodes(word):
        if part.get("Type") in QUOTED_PARTS and part.get("Dollar"):
            raise UnsupportedSyntax("dollar-quoted shell words require explicit review", "dollar-quote")
        if part.get("Type") == "ParamExp":
            dynamic |= not is_home_parameter(part)
        elif part.get("Type") in SUBSTITUTIONS:
            dynamic = True
        elif part.get("Type") not in WORD_PARTS:
            raise UnsupportedSyntax("shell expansions require explicit review", "expansion")
    parts = word.get("Parts", [])
    for index, part in enumerate(parts):
        if part.get("Type") == "Lit" and not is_literal_text(part.get("Value", ""), first=index == 0):
            dynamic = True
    if dynamic:
        return source_text(word, source), True
    return "".join(literal_part(index, part, source) for index, part in enumerate(parts)), False


def spreads(word: dict, source: bytes) -> bool:
    """Whether a word may become several words, or other words than the decoder sees.

    That is an unquoted expansion, substitution, glob, or brace, a line continuation, which the
    shell removes, or a positional parameter or array expansion even in quotes.
    """
    parts = word.get("Parts", [])
    unquoted = "".join(part.get("Value", "") for part in parts if part.get("Type") == "Lit")
    if any(part.get("Type") in SPLIT_PARTS for part in parts) or GLOB.search(unquoted) or BRACES & set(unquoted):
        return True
    if LINE_CONTINUATION in source_text(word, source):
        return True
    for part in word_nodes(word):
        if part.get("Type") != "ParamExp":
            continue
        name = part.get("Param", {}).get("Value", "")
        index = "".join(inner.get("Value", "") for inner in (part.get("Index") or {}).get("Parts", []))
        if name in SPREADING or name.isdigit() or index in SPREADING:
            return True
    return False


def word_nodes(value: object) -> Iterator[dict]:
    """Walk a word's parts without entering substitutions, whose commands parse judges separately."""
    if isinstance(value, dict):
        yield value
        if value.get("Type") in SUBSTITUTIONS:
            return
        for child in value.values():
            yield from word_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from word_nodes(child)


def is_home_parameter(part: dict) -> bool:
    """Accept a plain $HOME or ${HOME}; any modifier would compute a value the hook cannot predict."""
    name = part.get("Param", {}).get("Value")
    return name == HOME_PARAMETER and not any(part.get(key) for key in PARAMETER_MODIFIERS)


def is_literal_text(value: str, *, first: bool) -> bool:
    """Unquoted globs expand at run time, and so does a leading tilde unless it names the home directory."""
    if GLOB.search(value):
        return False
    if value.startswith("~"):
        return first and (value == "~" or value.startswith("~/"))
    return True


def literal_part(index: int, part: dict, source: bytes) -> str:
    """Decode one word part, substituting the home directory where the tree allowed it."""
    kind = part.get("Type")
    if kind == "ParamExp":
        return home_directory()
    if kind == "SglQuoted":
        return part.get("Value", "")
    if kind == "DblQuoted":
        return "".join(
            home_directory() if inner.get("Type") == "ParamExp" else unquoted('"' + source_text(inner, source) + '"')
            for inner in part.get("Parts", [])
        )
    value = unquoted(source_text(part, source))
    if index == 0 and value.startswith("~"):
        return home_directory() + value[1:]
    return value


def unquoted(text: str) -> str:
    """Decode an unquoted or double-quoted part as the shell does, dropping each line continuation."""
    try:
        values = shlex.split(text.replace(LINE_CONTINUATION, ""), posix=True)
    except ValueError as error:
        raise UnsupportedSyntax("a shell word could not be decoded unambiguously", "parse-failure") from error
    if len(values) != 1:
        raise UnsupportedSyntax("a shell word could not be decoded unambiguously", "parse-failure")
    return values[0]


def home_directory() -> str:
    home = os.path.expanduser("~")
    if home == "~":
        raise UnsupportedSyntax(
            "the home directory is unknown, so its expansion requires explicit review", "expansion"
        )
    return home


def nodes(value: object) -> Iterator[dict]:
    """Walk parser records without interpreting position metadata as executable code."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)
