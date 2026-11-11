"""Decode shfmt word nodes into literal values, or into source text the shell computes at run time."""

import re
import shlex
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

# Every command inside a substitution, clause, or function body is a CallExpr that parse judges on
# its own, so a body is judged where it is defined and a call by its own name; the substituted word
# itself is only known at run time.
SUBSTITUTIONS = frozenset({"CmdSubst", "ProcSubst", "ArithmExp"})
# A ParamExp other than the home directory makes its word a run-time word; Word is an operand inside it.
WORD_PARTS = frozenset({None, "Lit", "SglQuoted", "DblQuoted", "ParamExp", "Word"}) | SUBSTITUTIONS
QUOTED_PARTS = frozenset({"SglQuoted", "DblQuoted"})
HOME_PARAMETER = "HOME"
PARAMETER_MODIFIERS = ("Excl", "Length", "Width", "Index", "Slice", "Repl", "Names", "Exp")
# A word made only of simple parameters becomes no word at all when zsh finds them all empty.
WHOLLY_PARAMETERS = re.compile(r"(?:\$[A-Za-z_][A-Za-z0-9_]*|\$\{[A-Za-z_][A-Za-z0-9_]*\})+")
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
UNESCAPED_DOLLAR = re.compile(r"(?<!\\)\$")
# Inside double quotes the shell still expands or rewrites only these, `!` being history expansion.
DOUBLE_QUOTE_SPECIAL = re.compile(r"[$`\\!]")


class UnsupportedSyntaxError(ValueError):
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
            raise UnsupportedSyntaxError("dollar-quoted shell words require explicit review", "dollar-quote")
        if part.get("Type") == "ParamExp":
            dynamic |= not is_home_parameter(part)
        elif part.get("Type") in SUBSTITUTIONS:
            dynamic = True
        elif part.get("Type") not in WORD_PARTS:
            raise UnsupportedSyntaxError("shell expansions require explicit review", "expansion")
    parts = word.get("Parts", [])
    for index, part in enumerate(parts):
        if part.get("Type") == "Lit" and not is_literal_text(part.get("Value", ""), first=index == 0):
            dynamic = True
    if dynamic:
        return source_text(word, source), True
    return "".join(literal_part(index, part, source) for index, part in enumerate(parts)), False


def single_quoted_source(word: dict, source: bytes) -> str:
    r"""The word's source with each static quoted or escaped part rewritten in single quotes.

    A part holding an expansion, and any word that is dynamic or may spread, keeps its source text, so
    only text the shell passes through unchanged is respelled, so `-f body="x"` and `-f body=x\y`
    read as `-f body='x'` and `-f body='xy'`, which a rule can match whichever way the word was written.
    """
    text = source_text(word, source)
    parts = word.get("Parts", [])
    if literal_word(word, source)[1] or spreads(word, source):
        return text
    respelled = [_respelled_part(part, source) for part in parts]
    return text if any(part is None for part in respelled) else "".join(part or "" for part in respelled)


def _respelled_part(part: dict, source: bytes) -> str | None:
    text = source_text(part, source)
    kind = part.get("Type")
    if kind == "SglQuoted" and not part.get("Dollar"):
        return text
    if kind == "DblQuoted" and not part.get("Dollar"):
        body = text[1:-1]
        return None if DOUBLE_QUOTE_SPECIAL.search(body) else _single_quote(body)
    if kind == "Lit":
        return text if "\\" not in text else _respelled_escapes(text)
    return None


def _respelled_escapes(text: str) -> str:
    """Quote what an escaped unquoted text decodes to, keeping a plain `name=` prefix outside the quotes."""
    name, equals, rest = text.partition("=")
    if equals and "\\" not in name:
        return name + equals + _single_quote(unquoted(rest))
    return _single_quote(unquoted(text))


def _single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def spreads(word: dict, source: bytes, *, one_word_names: frozenset[str] = frozenset()) -> bool:
    """Whether a word may become several words, or other words than the decoder sees.

    That is an unquoted expansion, substitution, glob, or brace, a line continuation, which the
    shell removes, or a positional parameter or array expansion even in quotes. A plain unquoted
    `$name` or `${name}` of one of `one_word_names` is one word, as zsh does not split a value or glob
    its result; a `$` left in a literal part, such as `$=name` or `$~name`, is a zsh expansion either way.
    """
    parts = word.get("Parts", [])
    unquoted = "".join(part.get("Value", "") for part in parts if part.get("Type") == "Lit")
    if any(part.get("Type") in SPLIT_PARTS and not is_one_word_parameter(part, one_word_names) for part in parts):
        return True
    if GLOB.search(unquoted) or BRACES & set(unquoted) or UNESCAPED_DOLLAR.search(unquoted):
        return True
    if parts and parts[0].get("Type") == "Lit" and parts[0].get("Value", "").startswith("~"):
        return any(part.get("Type") == "ParamExp" for part in parts)
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


def is_one_word_parameter(part: dict, names: frozenset[str]) -> bool:
    """A plain `$name` or `${name}` of a listed variable, with no modifier, subscript, or flag."""
    return (
        part.get("Type") == "ParamExp"
        and part.get("Param", {}).get("Value", "") in names
        and not any(part.get(key) for key in PARAMETER_MODIFIERS)
    )


def vanishes_when_empty(word: str) -> bool:
    """Whether the source word is only simple parameters, so zsh drops it entirely when they are all empty."""
    return bool(WHOLLY_PARAMETERS.fullmatch(word))


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
        raise UnsupportedSyntaxError("a shell word could not be decoded unambiguously", "parse-failure") from error
    if len(values) != 1:
        raise UnsupportedSyntaxError("a shell word could not be decoded unambiguously", "parse-failure")
    return values[0]


def home_directory() -> str:
    """Return the home directory a `$HOME` or leading `~` expands to.

    Raises:
        UnsupportedSyntaxError: The system cannot tell the home directory, so the expansion needs review.
    """
    try:
        return str(Path.home())
    except RuntimeError as error:
        raise UnsupportedSyntaxError(
            "the home directory is unknown, so its expansion requires explicit review", "expansion"
        ) from error


def nodes(value: object) -> Iterator[dict]:
    """Walk parser records without interpreting position metadata as executable code."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)
