"""Find the text a builtin turns into code, and any change to what a command name runs."""

import re
from collections.abc import Callable

from shell_words import UnsupportedSyntaxError, nodes

# bash and zsh parameters whose elements define an alias or a function, or the file a command name runs.
CODE_PARAMETERS = frozenset(
    "aliases galiases saliases dis_aliases dis_galiases dis_saliases functions dis_functions commands "
    "BASH_ALIASES BASH_CMDS".split()
)
# Text naming an element of such a parameter, as printf -v or print -v assign to it, attached to an option or not.
CODE_ELEMENT = re.compile(rf"(?:^-[A-Za-z]*|(?<![A-Za-z0-9_]))(?:{'|'.join(CODE_PARAMETERS)})\[")
# Builtins that assign a whole parameter given by name, such as set -A or read -A.
ASSIGNING_BUILTINS = frozenset({"set", "read", "vared", "print", "printf", "getopts", "mapfile", "readarray"})
# Builtins whose operands all name parameters to assign.
NAME_OPERAND_BUILTINS = frozenset({"read", "vared", "mapfile", "readarray", "getopts"})
# An option whose next word names the parameter to assign: -v, -A, or -a, alone or ending a bundle.
NAME_OPTION = re.compile(r"-[A-Za-z]*[vAa]")
# The options trap takes; any other word before the signals is the action, as zsh reads it.
TRAP_OPTIONS = frozenset({"-l", "-p", "-P"})
# A function the text of eval or trap is judged inside, as it inherits input and arguments the hook does not see.
CODE_BODY = "__guard_code_text"
# The prefix of an environment variable bash imports as a function.
IMPORTED_FUNCTION = "BASH_FUNC_"


def scripts(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> list[str] | None:
    """Each literal script eval or trap runs, none for an alias or hash lookup; None for any other program.

    Raises:
        UnsupportedSyntaxError: The text is computed at run time, so no rule can judge it.
    """
    if names_code_parameter(arguments, dynamic) or any(IMPORTED_FUNCTION in argument for argument in arguments):
        raise UnsupportedSyntaxError(
            "defining an alias, a function, or a command path in the command requires explicit review", "wrapper"
        )
    reader = READERS.get(arguments[0])
    if reader is None:
        return None
    return [f"{CODE_BODY}() {{\n{script}\n}}" for script in reader(arguments, dynamic) if script.strip()]


def defines_code(record: dict) -> bool:
    """Whether a parser record assigns or expands a parameter that defines an alias, a function, or a command path.

    An assigned value naming one counts too, as a nameref or a later printf -v "$name" may write through it.
    """
    name = record.get("Name") or record.get("Param")
    value = "".join(part.get("Value", "") for part in nodes(record.get("Value")))
    if IMPORTED_FUNCTION in value:
        return True
    if not isinstance(name, dict):
        return False
    return name.get("Value") in CODE_PARAMETERS or value in CODE_PARAMETERS or bool(CODE_ELEMENT.search(value))


def names_code_parameter(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> bool:
    """Whether a call may assign such a parameter: an element of one, or one an assigning builtin is handed by name.

    A name computed at run time may be any of them.
    """
    if any(CODE_ELEMENT.search(argument) for argument in arguments[1:]):
        return True
    if arguments[0] not in ASSIGNING_BUILTINS:
        return False
    computed = any(dynamic[index] and _names_by(arguments, index) for index in range(1, len(arguments)))
    return computed or any(argument in CODE_PARAMETERS for argument in arguments[1:])


def _names_by(arguments: tuple[str, ...], index: int) -> bool:
    """Whether the word at the index names a parameter: any operand of read and its kind, an option, or a -v value."""
    word = arguments[index]
    return (
        arguments[0] in NAME_OPERAND_BUILTINS or word[:1] == "-" or bool(NAME_OPTION.fullmatch(arguments[index - 1]))
    )


def _eval_scripts(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> list[str]:
    start = 2 if arguments[1:2] == ("--",) else 1
    if any(dynamic[start:]):
        raise UnsupportedSyntaxError("eval of a computed script requires explicit review", "wrapper")
    return [" ".join(arguments[start:])]


def _trap_scripts(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> list[str]:
    """The first word after the options, when a signal follows it; one word alone, or the action `-`, only resets."""
    index = 1
    while index < len(arguments) and arguments[index] in TRAP_OPTIONS:
        index += 1
    index += int(index < len(arguments) and arguments[index] == "--")
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
    if any(dynamic[1:]) or any(
        "=" in argument or (argument[:1] == "-" and "p" in argument) for argument in arguments[1:]
    ):
        raise UnsupportedSyntaxError("a command path set in the command requires explicit review", "wrapper")
    return []


READERS: dict[str, Callable[[tuple[str, ...], tuple[bool, ...]], list[str]]] = {
    "eval": _eval_scripts,
    "trap": _trap_scripts,
    "alias": _alias_scripts,
    "hash": _hash_scripts,
}
