"""Find the text a builtin turns into code, now or whenever a signal or an alias name comes up."""

from collections.abc import Callable

from shell_words import UnsupportedSyntaxError


def scripts(arguments: tuple[str, ...], dynamic: tuple[bool, ...]) -> list[str] | None:
    """Each literal script eval, trap, or alias runs; None for any other program.

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
    """The value of each definition; a lookup without `=` has an empty value."""
    found = []
    for argument, computed in zip(arguments[1:], dynamic[1:], strict=True):
        if computed:
            raise UnsupportedSyntaxError("an alias computed at run time requires explicit review", "wrapper")
        name, _, value = argument.partition("=")
        if not name.startswith("-"):
            found.append(value)
    return found


READERS: dict[str, Callable[[tuple[str, ...], tuple[bool, ...]], list[str]]] = {
    "eval": _eval_scripts,
    "trap": _trap_scripts,
    "alias": _alias_scripts,
}
