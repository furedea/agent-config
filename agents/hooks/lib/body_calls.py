"""Walk a function body: the calls it makes, the programs they run, and the assignments in it."""

import re
from pathlib import Path

import respelling
import shell_input
from shell_words import literal_word, nodes

# Words before a builtin that still run it, as in builtin shift, command -p shift, or zsh's noglob shift.
BUILTIN_PREFIXES = frozenset({"builtin", "command", "noglob", "nocorrect", "-"})
# A program name that runs a shell, which may read its script's data from its input.
SHELL_NAME = re.compile(r"\w*sh|fish|pwsh")


def program_words(call: dict, data: bytes) -> list[tuple[str, bool]]:
    """The call's decoded words with their run-time flags, from the program on, past builtin and command."""
    words = [literal_word(word, data) for word in call["Args"]]
    while len(words) > 1 and words[0][0] in BUILTIN_PREFIXES:
        words = words[1:]
        while len(words) > 1 and words[0][0][:1] == "-":
            words = words[1:]
    return words


def program(call: dict, data: bytes) -> list[str]:
    """The call's words as the shell runs them, from the program on, past builtin, command, and command's options."""
    return [value for value, _ in program_words(call, data)]


def calls(body: dict, data: bytes, name: str | None = None) -> list[dict]:
    """The body's calls, or only those running the named program."""
    found = (node for node in nodes(body) if node.get("Type") == "CallExpr" and node.get("Args"))
    return [call for call in found if name is None or program(call, data)[0] == name]


def assignments(body: dict) -> list[dict]:
    """The body's assignments of a single value."""
    return [
        node for node in nodes(body) if "Type" not in node and "Name" in node and isinstance(node.get("Value"), dict)
    ]


def statements(body: dict) -> list[dict]:
    """The statements of the body that run one call, together with their redirections."""
    return [
        node for node in nodes(body) if isinstance(node.get("Cmd"), dict) and node["Cmd"].get("Type") == "CallExpr"
    ]


def respelled_nodes(statement: dict) -> list[dict]:
    """The call's assignments, words, and the targets of its redirections other than heredocs."""
    return [
        *statement["Cmd"].get("Assigns", []),
        *statement["Cmd"].get("Args", []),
        *(redirect["Word"] for redirect in respelling.redirections(statement)),
    ]


def may_run_shell(call: dict, data: bytes) -> bool:
    """Whether the call may run a shell: a word names one, or the program is known only at run time."""
    words = program_words(call, data)
    index = shell_input.program_index([value for value, _ in words])
    if index < len(words) and words[index][1]:
        return True
    # A wrapper's option operand may sit where the program seems to be, so any word naming a shell counts.
    return any(SHELL_NAME.fullmatch(Path(value).name) for value, _ in words)
