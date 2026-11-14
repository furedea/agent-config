"""Find the text a builtin turns into code, and any change to what a command name runs."""

import re
from collections.abc import Callable

from shell_words import UnsupportedSyntaxError

# bash and zsh parameters whose elements define an alias or a function, or the file a command name runs.
CODE_PARAMETERS = frozenset(
    "aliases galiases saliases dis_aliases dis_galiases dis_saliases functions dis_functions commands "
    "BASH_ALIASES BASH_CMDS".split()
)
# A word naming an element of such a parameter, as printf -v or print -v assign to it.
CODE_ELEMENT = re.compile(rf"(?:{'|'.join(CODE_PARAMETERS)})\[")
# Builtins that assign a whole parameter given by name, such as set -A or read -A.
ASSIGNING_BUILTINS = frozenset({"set", "read", "vared", "print", "printf", "getopts", "mapfile", "readarray"})


def scripts(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> list[str] | None:
    """Each literal script eval or trap runs, none for an alias or hash lookup; None for any other program.

    Raises:
        UnsupportedSyntaxError: The text is computed at run time, so no rule can judge it.
    """
    if names_code_parameter(arguments):
        raise UnsupportedSyntaxError("a call that may define an alias, a function, or a command path needs review")
    reader = READERS.get(arguments[0])
    return None if reader is None else reader(arguments, dynamic)


def defines_code(record: dict) -> bool:
    """Whether a parser record assigns or expands a parameter that defines an alias, a function, or a command path."""
    name = record.get("Name") or record.get("Param")
    return isinstance(name, dict) and name.get("Value") in CODE_PARAMETERS


def names_code_parameter(arguments: tuple[str, ...]) -> bool:
    """Whether a call may assign such a parameter: an element of one, or a whole one handed to an assigning builtin."""
    if any(CODE_ELEMENT.match(argument) for argument in arguments[1:]):
        return True
    return arguments[0] in ASSIGNING_BUILTINS and any(argument in CODE_PARAMETERS for argument in arguments[1:])


def _eval_scripts(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> list[str]:
    if any(dynamic[1:]):
        raise UnsupportedSyntaxError("eval of a computed script requires explicit review", "wrapper")
    return [" ".join(arguments[1:])]


def _trap_scripts(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> list[str]:
    """The first operand, when a signal follows it; one operand alone, or the action `-`, only resets."""
    index = 1
    while index < len(arguments) and arguments[index].startswith("-") and arguments[index] != "-":
        index += 1
        if arguments[index - 1] == "--":
            break
    if len(arguments) - index < 2 or arguments[index] == "-":
        return []
    if dynamic[index]:
        raise UnsupportedSyntaxError("a trap action computed at run time requires explicit review", "wrapper")
    return [arguments[index]]


def _alias_scripts(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> list[str]:
    """None for a lookup; a definition asks, since its value joins whatever words later follow its name."""
    if any(dynamic[1:]) or any("=" in argument for argument in arguments[1:]):
        raise UnsupportedSyntaxError("an alias defined in the command requires explicit review", "wrapper")
    return []


def _hash_scripts(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> list[str]:
    """None for a lookup or a reset; giving a name its own path asks, as -p in bash or name=path in zsh do."""
    if any(dynamic[1:]) or any(argument.startswith("-p") or "=" in argument for argument in arguments[1:]):
        raise UnsupportedSyntaxError("a command path set in the command requires explicit review", "wrapper")
    return []


READERS: dict[str, Callable[[tuple[str, ...], tuple[bool, ...]], list[str]]] = {
    "eval": _eval_scripts,
    "trap": _trap_scripts,
    "alias": _alias_scripts,
    "hash": _hash_scripts,
}
