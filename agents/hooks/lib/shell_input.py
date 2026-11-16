"""Find the scripts a shell reads from its standard input: a pipe, a heredoc, a here-string, or a file."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from shell_words import UnsupportedSyntaxError, literal_word, nodes, source_text, spreads
from shell_wrappers import ASSIGNMENT, WRAPPERS

# Options of echo, which writes its remaining arguments; the backslash escapes they toggle are refused.
ECHO_OPTIONS = re.compile(r"-[neE]+")
# A word that changes the working directory, once spelling, underscores, and case are gone: a cd builtin, zsh's
# auto_cd option, or anything that sets options, which may turn it on.
DIRECTORY_CHANGE = re.compile(r"(?<![\w-])(?:cd|pushd|popd|chdir|autocd|setopt|emulate|options\[)")
# Words before a program that still run it, so a program named only at run time behind them may be cd.
PROGRAM_PREFIXES = frozenset({"builtin", "command", "noglob", "nocorrect", "-", "exec", "time"})
# Line continuations, quotes, escapes, and underscores, which spell a word or a zsh option without writing it plainly.
SPELLING = re.compile(r"\\\n|[\\'\"_]")
# Text eval or trap runs that may read or replace a function's arguments, at any depth of eval, once unquoted;
# an argument array counts wherever its name appears, as an element like argv[1] loses its brackets.
ARGUMENT_TEXT = re.compile(
    r"[$`]|argv|BASH_ARG[VC]|(?<![\w-])\d+\+?=|(?<![\w-])(?:shift|set|getopts|zparseopts|read|mapfile|readarray|vared|source|\.)(?![\w-])"
)
# Quotes, escapes, braces, and glob characters, which spell a word in code text without writing it plainly.
CODE_SPELLING = re.compile(r"[\\'\"{},?*\[\]]")
# An input redirection, with the descriptor it replaces; only descriptor 0 is the shell's script.
INPUT_REDIRECTION = re.compile(r"(\d*)(<<<|<<|<&|<>|<(?!\())")


@dataclass(frozen=True, slots=True)
class InputSources:
    """Where each statement of one parsed source reads its standard input from.

    `feeds` maps a statement on the reading side of a pipe to the statement writing into it, and
    `enclosing` maps a statement inside a compound command, such as `( ... )` or `{ ...; }`, to the
    compound statement whose input redirection it inherits. Records list an outer node before the
    nodes inside it, so the nearest source wins. `in_functions` maps each statement of a function
    body to that body; such a statement inherits whatever input each call of the function is given,
    so only a source inside the same body is its own.
    """

    data: bytes
    feeds: dict[int, dict]
    enclosing: dict[int, dict]
    in_functions: dict[int, int] = field(default_factory=dict)

    @classmethod
    def of(cls, records: tuple[dict, ...], data: bytes) -> Self:
        """Index the records of one parsed source, outer nodes first, so each statement's input source is known."""
        pipes = (node for node in records if node.get("Type") == "BinaryCmd" and is_pipe(node, data))
        feeds = {id(statement): pipe["X"] for pipe in pipes for statement in nodes(pipe["Y"]) if "Cmd" in statement}
        compounds = (
            node
            for node in records
            if "Cmd" in node and node["Cmd"].get("Type") != "CallExpr" and _redirected_inputs(node, data)
        )
        enclosing = {
            id(statement): compound
            for compound in compounds
            for statement in nodes(compound["Cmd"])
            if "Cmd" in statement
        }
        bodies = (node["Body"] for node in records if node.get("Type") == "FuncDecl")
        in_functions = {id(statement): id(body) for body in bodies for statement in nodes(body) if "Cmd" in statement}
        return cls(data, feeds, enclosing, in_functions)

    def scripts(self, owner: dict, directories: tuple[Path | None, ...]) -> list[str]:
        """Return each script a shell statement may read from its standard input, to be judged one by one.

        A `<(...)` argument, both a pipe and an inherited redirection whose order the hook does not
        track, or no source of its own inside a function body, leave the script to run time, so they
        are refused rather than guessed.
        """
        if _reads_process_substitution(owner.get("Cmd", owner), self.data):
            raise _computed_input()
        if _redirected_inputs(owner, self.data):
            return redirected_scripts(owner, self.data, directories)
        outer, feed = self._own(owner, self.enclosing.get(id(owner))), self._own(owner, self.feeds.get(id(owner)))
        if outer is not None and feed is not None:
            raise _computed_input()
        if outer is not None:
            return redirected_scripts(outer, self.data, directories)
        if feed is None and id(owner) in self.in_functions:
            raise _computed_input()
        return [piped_script(feed, self.data)] if feed is not None else []

    def _own(self, owner: dict, source: dict | None) -> dict | None:
        """The source, unless the statement sits in a function body that the source lies outside of."""
        body = self.in_functions.get(id(owner))
        return source if source is None or body is None or self.in_functions.get(id(source)) == body else None


def is_pipe(node: dict, data: bytes) -> bool:
    """Whether a binary command is a pipe (| or |&), judged by its operator text, not by parser codes."""
    offset = node["OpPos"]["Offset"]
    return data[offset : offset + 1] == b"|" and data[offset + 1 : offset + 2] != b"|"


def _redirected_inputs(statement: dict, data: bytes) -> list[tuple[dict, str]]:
    operators = ((redirect, _stdin_operator(redirect, data)) for redirect in statement.get("Redirs", []))
    return [(redirect, operator) for redirect, operator in operators if operator]


def redirected_scripts(statement: dict, data: bytes, directories: tuple[Path | None, ...]) -> list[str]:
    """Return the scripts a redirection of standard input supplies; a duplicated or repeated one is refused."""
    inputs = _redirected_inputs(statement, data)
    if len(inputs) > 1:
        raise _computed_input()
    redirect, operator = inputs[0]
    if operator == "<<":
        return [heredoc_text(redirect)]
    if operator == "<<<":
        return [_static_script(redirect["Word"], data) + "\n"]
    if operator != "<":
        raise _computed_input()
    return file_scripts(Path(_static_script(redirect["Word"], data)), directories)


def _stdin_operator(redirect: dict, data: bytes) -> str:
    match = INPUT_REDIRECTION.match(source_text(redirect, data))
    return match.group(2) if match and int(match.group(1) or "0") == 0 else ""


def _reads_process_substitution(node: dict, data: bytes) -> bool:
    parts = (part for word in node.get("Args", []) for part in word.get("Parts", []))
    return any(part.get("Type") == "ProcSubst" and source_text(part, data).startswith("<(") for part in parts)


def heredoc_text(redirect: dict) -> str:
    """Return the static script of a heredoc, refusing one the shell computes."""
    parts = redirect["Hdoc"].get("Parts", [])
    if any(part.get("Type") != "Lit" for part in parts):
        raise UnsupportedSyntaxError("a shell heredoc whose text is computed requires explicit review", "heredoc")
    return "".join(part.get("Value", "") for part in parts)


def file_scripts(path: Path, directories: tuple[Path | None, ...]) -> list[str]:
    """Read a script file now, in every directory the shell may run in; refuse one that cannot be found.

    Only a regular file is read, so a FIFO or device cannot stall the hook.
    """
    if path.is_absolute():
        candidates = [path]
    elif None in directories:
        raise _computed_input()
    else:
        candidates = [directory / path for directory in directories if directory]
    try:
        scripts = [candidate.read_text() for candidate in candidates if candidate.is_file()]
    except (OSError, UnicodeDecodeError) as error:
        raise _computed_input() from error
    if not scripts:
        raise _computed_input()
    return scripts


def piped_script(statement: dict, data: bytes) -> str:
    """Return the text a literal echo or plain printf writes into the pipe, refusing any other source."""
    command = statement.get("Cmd") or {}
    # A word the shell splits or expands, braces included, writes other text than the hook decodes.
    if (
        command.get("Type") != "CallExpr"
        or not command.get("Args")
        or any(spreads(word, data) for word in command["Args"])
    ):
        raise _computed_input()
    program, *arguments = (_static_script(word, data) for word in command["Args"])
    name = Path(program).name
    if name == "echo":
        while arguments and ECHO_OPTIONS.fullmatch(arguments[0]):
            arguments.pop(0)
        text = " ".join(arguments)
    elif name == "printf" and len(arguments) == 1 and "%" not in arguments[0]:
        text = arguments[0]
    else:
        raise _computed_input()
    # echo and printf may turn a backslash escape into a line break, which separates commands.
    if "\\" in text:
        raise _computed_input()
    return text


def _static_script(word: dict, data: bytes) -> str:
    value, dynamic = literal_word(word, data)
    if dynamic:
        raise _computed_input()
    return value


def _computed_input() -> UnsupportedSyntaxError:
    return UnsupportedSyntaxError(
        "running a shell on a script read from computed or inherited input requires explicit review", "wrapper"
    )


def input_scripts(read: Callable[[], list[str]], tolerant: bool) -> list[str] | None:
    """The scripts a shell reads from its input; None when a tolerant caller marks its call for review instead."""
    try:
        return read()
    except UnsupportedSyntaxError:
        if tolerant:
            return None
        raise


def moves_directory(source: str, records: tuple[dict, ...]) -> bool:
    """Whether the source may change directory anywhere, so a body run later may run somewhere unknown.

    A program named only at run time may be cd, and set -J turns on zsh's auto_cd, as -o autocd does.
    """
    if DIRECTORY_CHANGE.search(normalized(source)):
        return True
    data = source.encode()
    calls = [node for node in records if node.get("Type") == "CallExpr" and node.get("Args")]
    if any(word[:1] in {"-", "+"} and "j" in word for word in options_given_to_set(calls, data)):
        return True
    return any(runs_unseen(call, data) for call in calls)


def normalized(text: str) -> str:
    """The text without line continuations, quotes, escapes, underscores, or case, as zsh reads option names."""
    return SPELLING.sub("", text).lower()


def options_given_to_set(calls: list[dict], data: bytes) -> list[str]:
    """The option words, normalized, that each set call gives, past prefixes and wrappers, with the names -o takes."""
    options = []
    for call in calls:
        decoded = [literal_word(word, data) for word in call["Args"]]
        # A word known only at run time may give any option, so it stands as -aj, the letters that matter.
        words = ["-aj" if dynamic else normalized(value) for value, dynamic in decoded]
        words = words[program_index(words) :]
        if words and words[0] == "set":
            options += [word for word in words[1:] if word[:1] in {"-", "+"} or word.isalpha()]
    return options


def program_index(words: list[str]) -> int:
    """Where the program sits, past prefixes, wrappers, options, and assignments."""
    for index, value in enumerate(words):
        if not _passes_over(value):
            return index
    return len(words)


def _passes_over(value: str) -> bool:
    return (
        value in PROGRAM_PREFIXES
        or value[:1] in {"-", "+"}
        or Path(value).name in WRAPPERS
        or ASSIGNMENT.match(value) is not None
    )


def runs_unseen(call: dict, data: bytes) -> bool:
    """Whether the program, past prefixes, wrappers, options, and assignments, is named only at run time."""
    for value, dynamic in (literal_word(word, data) for word in call["Args"]):
        if dynamic:
            return True
        if not _passes_over(value):
            return False
    return False


def unpassed(scripts: list[str], passed: tuple[str, ...]) -> list[str]:
    """The scripts a shell runs, unless one may read the arguments the shell is handed after them.

    Raises:
        UnsupportedSyntaxError: A script reads arguments that the nested judgement cannot see.
    """
    if passed and any(ARGUMENT_TEXT.search(CODE_SPELLING.sub("", script)) for script in scripts):
        raise UnsupportedSyntaxError(
            "running a shell script that reads arguments passed to it requires explicit review"
        )
    return scripts


def operands(arguments: tuple[str, ...]) -> tuple[str, ...]:
    """The words a shell takes as arguments: from its first non-option word, or after a - or -- ending options."""
    for index, argument in enumerate(arguments[1:], 1):
        if argument in {"-", "--"}:
            return arguments[index + 1 :]
        if argument[:1] not in {"-", "+"}:
            return arguments[index:]
    return ()
