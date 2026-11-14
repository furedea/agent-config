"""Find the text a builtin turns into code, now or whenever a signal or an alias name comes up."""

from collections.abc import Callable

from shell_words import UnsupportedSyntaxError


def scripts(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> list[str] | None:
    """Each literal script eval or trap runs, none for an alias lookup; None for any other program.

    Raises:
        UnsupportedSyntaxError: The text is computed at run time, so no rule can judge it.
    """
    reader = READERS.get(arguments[0])
    return None if reader is None else reader(arguments, dynamic)


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
    if any(dynamic[1:]) or any("=" in argument and not argument.startswith("-") for argument in arguments[1:]):
        raise UnsupportedSyntaxError("an alias defined in the command requires explicit review", "wrapper")
    return []


READERS: dict[str, Callable[[tuple[str, ...], tuple[bool, ...]], list[str]]] = {
    "eval": _eval_scripts,
    "trap": _trap_scripts,
    "alias": _alias_scripts,
}
