"""Find the scripts a shell reads from its standard input: a pipe, a heredoc, a here-string, or a file."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Self

from shell_words import UnsupportedSyntax, literal_word, nodes, source_text, spreads


# Options of echo, which writes its remaining arguments; the backslash escapes they toggle are refused.
ECHO_OPTIONS = re.compile(r"-[neE]+")
# An input redirection, with the descriptor it replaces; only descriptor 0 is the shell's script.
INPUT_REDIRECTION = re.compile(r"(\d*)(<<<|<<|<&|<>|<(?!\())")


@dataclass(frozen=True, slots=True)
class InputSources:
    """Where each statement of one parsed source reads its standard input from.

    `feeds` maps a statement on the reading side of a pipe to the statement writing into it, and
    `enclosing` maps a statement inside a compound command, such as `( ... )` or `{ ...; }`, to the
    compound statement whose input redirection it inherits. Records list an outer node before the
    nodes inside it, so the nearest source wins.
    """

    data: bytes
    feeds: dict[int, dict]
    enclosing: dict[int, dict]

    @classmethod
    def of(cls, records: tuple[dict, ...], data: bytes) -> Self:
        pipes = (node for node in records if node.get("Type") == "BinaryCmd" and is_pipe(node, data))
        feeds = {id(statement): pipe["X"] for pipe in pipes for statement in nodes(pipe["Y"]) if "Cmd" in statement}
        compounds = (
            node
            for node in records
            if "Cmd" in node and node["Cmd"].get("Type") != "CallExpr" and redirected_inputs(node, data)
        )
        enclosing = {
            id(statement): compound
            for compound in compounds
            for statement in nodes(compound["Cmd"])
            if "Cmd" in statement
        }
        return cls(data, feeds, enclosing)

    def scripts(self, owner: dict, directories: tuple[Path | None, ...]) -> list[str]:
        """Return each script a shell statement may read from its standard input, to be judged one by one.

        A `<(...)` argument, or both a pipe and an inherited redirection whose order the hook does
        not track, leave the script to run time, so they are refused rather than guessed.
        """
        if reads_process_substitution(owner.get("Cmd", owner), self.data):
            raise computed_input()
        if redirected_inputs(owner, self.data):
            return redirected_scripts(owner, self.data, directories)
        outer, feed = self.enclosing.get(id(owner)), self.feeds.get(id(owner))
        if outer is not None and feed is not None:
            raise computed_input()
        if outer is not None:
            return redirected_scripts(outer, self.data, directories)
        return [piped_script(feed, self.data)] if feed is not None else []


def is_pipe(node: dict, data: bytes) -> bool:
    """Whether a binary command is a pipe (| or |&), judged by its operator text, not by parser codes."""
    offset = node["OpPos"]["Offset"]
    return data[offset : offset + 1] == b"|" and data[offset + 1 : offset + 2] != b"|"


def redirected_inputs(statement: dict, data: bytes) -> list[tuple[dict, str]]:
    operators = ((redirect, stdin_operator(redirect, data)) for redirect in statement.get("Redirs", []))
    return [(redirect, operator) for redirect, operator in operators if operator]


def redirected_scripts(statement: dict, data: bytes, directories: tuple[Path | None, ...]) -> list[str]:
    """Return the scripts a redirection of standard input supplies; a duplicated or repeated one is refused."""
    inputs = redirected_inputs(statement, data)
    if len(inputs) > 1:
        raise computed_input()
    redirect, operator = inputs[0]
    if operator == "<<":
        return [heredoc_text(redirect)]
    if operator == "<<<":
        return [static_script(redirect["Word"], data) + "\n"]
    if operator != "<":
        raise computed_input()
    return file_scripts(Path(static_script(redirect["Word"], data)), directories)


def stdin_operator(redirect: dict, data: bytes) -> str:
    match = INPUT_REDIRECTION.match(source_text(redirect, data))
    return match.group(2) if match and int(match.group(1) or "0") == 0 else ""


def reads_process_substitution(node: dict, data: bytes) -> bool:
    parts = (part for word in node.get("Args", []) for part in word.get("Parts", []))
    return any(part.get("Type") == "ProcSubst" and source_text(part, data).startswith("<(") for part in parts)


def heredoc_text(redirect: dict) -> str:
    """Return the static script of a heredoc, refusing one the shell computes."""
    parts = redirect["Hdoc"].get("Parts", [])
    if any(part.get("Type") != "Lit" for part in parts):
        raise UnsupportedSyntax("a shell heredoc whose text is computed requires explicit review", "heredoc")
    return "".join(part.get("Value", "") for part in parts)


def file_scripts(path: Path, directories: tuple[Path | None, ...]) -> list[str]:
    """Read a script file now, in every directory the shell may run in; refuse one that cannot be found.

    Only a regular file is read, so a FIFO or device cannot stall the hook.
    """
    if path.is_absolute():
        candidates = [path]
    elif None in directories:
        raise computed_input()
    else:
        candidates = [directory / path for directory in directories if directory]
    try:
        scripts = [candidate.read_text() for candidate in candidates if candidate.is_file()]
    except (OSError, UnicodeDecodeError) as error:
        raise computed_input() from error
    if not scripts:
        raise computed_input()
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
        raise computed_input()
    program, *arguments = (static_script(word, data) for word in command["Args"])
    name = Path(program).name
    if name == "echo":
        while arguments and ECHO_OPTIONS.fullmatch(arguments[0]):
            arguments.pop(0)
        text = " ".join(arguments)
    elif name == "printf" and len(arguments) == 1 and "%" not in arguments[0]:
        text = arguments[0]
    else:
        raise computed_input()
    # echo and printf may turn a backslash escape into a line break, which separates commands.
    if "\\" in text:
        raise computed_input()
    return text


def static_script(word: dict, data: bytes) -> str:
    value, dynamic = literal_word(word, data)
    if dynamic:
        raise computed_input()
    return value


def computed_input() -> UnsupportedSyntax:
    return UnsupportedSyntax("a shell reading a computed script from its input requires explicit review", "wrapper")
