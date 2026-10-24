"""Find the script a shell reads from its standard input: a pipe, a heredoc, a here-string, or a file."""

from pathlib import Path
import re

from shell_words import UnsupportedSyntax, literal_word, nodes, source_text


# Options of echo, which writes its remaining arguments; the backslash escapes they toggle are refused.
ECHO_OPTIONS = re.compile(r"-[neE]+")
# An input redirection, with the descriptor it replaces; only descriptor 0 is the shell's script.
INPUT_REDIRECTION = re.compile(r"(\d*)(<<<|<<|<&|<>|<(?!\())")


def pipe_feeds(records: tuple[dict, ...], data: bytes) -> dict[int, dict]:
    """Map each statement on the reading side of a pipe to the statement whose output it reads.

    Records list an outer pipeline before the pipelines inside it, so the nearest pipe wins.
    """
    pipes = (node for node in records if node.get("Type") == "BinaryCmd" and is_pipe(node, data))
    return {id(statement): pipe["X"] for pipe in pipes for statement in nodes(pipe["Y"]) if "Cmd" in statement}


def is_pipe(node: dict, data: bytes) -> bool:
    """Whether a binary command is a pipe (| or |&), judged by its operator text, not by parser codes."""
    offset = node["OpPos"]["Offset"]
    return data[offset : offset + 1] == b"|" and data[offset + 1 : offset + 2] != b"|"


def redirected_script(owner: dict, data: bytes, directories: tuple[Path | None, ...]) -> str:
    """Return the script a redirection of the shell's standard input supplies, or "" without one.

    A `<(...)` argument, a duplicated descriptor, or several redirections of standard input leave
    the script to run time, so they are refused rather than guessed.
    """
    operators = [(redirect, stdin_operator(redirect, data)) for redirect in owner.get("Redirs", [])]
    inputs = [(redirect, operator) for redirect, operator in operators if operator]
    if reads_process_substitution(owner.get("Cmd", owner), data) or len(inputs) > 1:
        raise computed_input()
    if not inputs:
        return ""
    redirect, operator = inputs[0]
    if operator == "<<":
        return heredoc_text(redirect)
    if operator == "<<<":
        return static_script(redirect["Word"], data) + "\n"
    if operator != "<":
        raise computed_input()
    return file_scripts(Path(static_script(redirect["Word"], data)), directories)


def stdin_operator(redirect: dict, data: bytes) -> str:
    match = INPUT_REDIRECTION.match(source_text(redirect, data))
    return match.group(2) if match and match.group(1) in {"", "0"} else ""


def reads_process_substitution(node: dict, data: bytes) -> bool:
    parts = (part for word in node["Args"] for part in word.get("Parts", []))
    return any(part.get("Type") == "ProcSubst" and source_text(part, data).startswith("<(") for part in parts)


def heredoc_text(redirect: dict) -> str:
    """Return the static script of a heredoc, refusing one the shell computes."""
    parts = redirect["Hdoc"].get("Parts", [])
    if any(part.get("Type") != "Lit" for part in parts):
        raise UnsupportedSyntax("a shell heredoc whose text is computed requires explicit review", "heredoc")
    return "".join(part.get("Value", "") for part in parts)


def file_scripts(path: Path, directories: tuple[Path | None, ...]) -> str:
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
    return "".join(scripts)


def piped_script(statement: dict | None, data: bytes) -> str:
    """Return the text a literal echo or plain printf writes into the pipe, refusing any other source."""
    if statement is None:
        return ""
    command = statement.get("Cmd") or {}
    if command.get("Type") != "CallExpr" or not command.get("Args"):
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
