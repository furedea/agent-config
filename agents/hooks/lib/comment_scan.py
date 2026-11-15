"""Find the comments in source text across lines, as a lexer would, without parsing the language.

A comment opener inside a string, and a string quote inside a comment, are skipped. The scan is approximate: a
construct it does not know is read as code, so a caller that compares two texts sees the same misreading in both.
"""

import re
from dataclasses import dataclass

HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


@dataclass(frozen=True, slots=True)
class Delimited:
    """A string or block comment from `opener` to `closer`; a single-line one also ends at a newline."""

    opener: str
    closer: str
    multiline: bool = False
    escapes: bool = True


@dataclass(frozen=True, slots=True)
class Syntax:
    """How one language writes comments and strings; earlier entries win when openers share a prefix."""

    line_comments: tuple[str, ...]
    block_comments: tuple[Delimited, ...] = ()
    strings: tuple[Delimited, ...] = ()
    heredocs: bool = False


C_BLOCK = (Delimited("/*", "*/", multiline=True),)
QUOTED = (Delimited('"', '"'), Delimited("'", "'"))
JAVASCRIPT = Syntax(("//",), C_BLOCK, (Delimited("`", "`", multiline=True), *QUOTED))
SYNTAXES = {
    **dict.fromkeys(
        (".py", ".pyi"),
        Syntax(("#",), (), (Delimited('"""', '"""', True), Delimited("'''", "'''", True), *QUOTED)),
    ),
    **dict.fromkeys((".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"), JAVASCRIPT),
    ".go": Syntax(("//",), C_BLOCK, (Delimited("`", "`", multiline=True, escapes=False), *QUOTED)),
    # A quote also starts a Rust lifetime, so only double-quoted strings are read.
    ".rs": Syntax(("//",), C_BLOCK, (Delimited('"', '"', multiline=True),)),
    **dict.fromkeys(
        (".sh", ".bash"),
        Syntax(
            ("#",), (), (Delimited("'", "'", True, escapes=False), Delimited('"', '"', multiline=True)), heredocs=True
        ),
    ),
    ".lua": Syntax(
        ("--",), (Delimited("--[[", "]]", multiline=True),), (Delimited("[[", "]]", True, escapes=False), *QUOTED)
    ),
    ".nix": Syntax(("#",), C_BLOCK, (Delimited("''", "''", multiline=True), Delimited('"', '"', multiline=True))),
}
HASH_COMMENTS = Syntax(("#",), (), QUOTED)


def comment_spans(text: str, suffix: str) -> list[tuple[int, int]]:
    """The start and end offsets of each comment in `text`, read with the syntax of files ending in `suffix`."""
    syntax = SYNTAXES.get(suffix, HASH_COMMENTS)
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(text):
        if syntax.heredocs and (heredoc := HEREDOC.match(text, index)):
            end = _heredoc_end(text, index, heredoc.group(2))
        elif block := _opening(text, index, syntax.block_comments):
            end = _delimited_end(text, index + len(block.opener), block)
            spans.append((index, end))
        elif text.startswith(syntax.line_comments, index):
            end = _line_end(text, index)
            spans.append((index, end))
        elif string := _opening(text, index, syntax.strings):
            end = _delimited_end(text, index + len(string.opener), string)
        else:
            end = index + 1
        index = end
    return spans


def _opening(text: str, index: int, candidates: tuple[Delimited, ...]) -> Delimited | None:
    return next((candidate for candidate in candidates if text.startswith(candidate.opener, index)), None)


def _delimited_end(text: str, index: int, delimited: Delimited) -> int:
    """The offset just past the closer, or where a single-line construct stops at a newline or the text ends."""
    while index < len(text):
        if delimited.escapes and text[index] == "\\":
            index += 2
        elif text.startswith(delimited.closer, index):
            return index + len(delimited.closer)
        elif text[index] == "\n" and not delimited.multiline:
            return index
        else:
            index += 1
    return len(text)


def _heredoc_end(text: str, index: int, word: str) -> int:
    """The offset past the line that holds only `word`, after the line that opens the heredoc."""
    terminator = re.compile(rf"^[ \t]*{re.escape(word)}[ \t]*$", re.MULTILINE)
    found = terminator.search(text, _line_end(text, index))
    return len(text) if found is None else found.end()


def _line_end(text: str, index: int) -> int:
    end = text.find("\n", index)
    return len(text) if end < 0 else end
