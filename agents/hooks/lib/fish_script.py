"""Find the script file a fish call runs, so its text can be read for what it would deny."""

from pathlib import Path

import shell_input
from shell_words import UnsupportedSyntax


# fish options that take a value: -C, -c, -d, -o, -f, -D, -p and their long forms.
VALUED_LETTERS = "CcdofDp"
VALUED_LONG_OPTIONS = frozenset(
    {
        "--init-command",
        "--command",
        "--debug",
        "--debug-output",
        "--features",
        "--debug-stack-frames",
        "--profile",
        "--profile-startup",
    }
)


def file_scripts(
    arguments: tuple[str, ...], dynamic: tuple[bool, ...], directories: tuple[Path | None, ...]
) -> list[str]:
    """The text of the script file a fish call runs; a file that cannot be read is left to the name-based review."""
    index = script_index(arguments)
    if index is None or dynamic[index]:
        return []
    try:
        return shell_input.file_scripts(Path(arguments[index]), directories)
    except UnsupportedSyntax:
        return []


def script_index(arguments: tuple[str, ...]) -> int | None:
    """Where the script file sits: the first operand past fish's options and their values; -c supplies no file."""
    index = 1
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            return index + 1 if index + 1 < len(arguments) else None
        if not argument.startswith("-"):
            return index
        if argument == "-" or runs_command(argument):
            return None
        index += 2 if takes_next_word(argument) else 1
    return None


def runs_command(argument: str) -> bool:
    """Whether the option is -c or --command, or an abbreviation of it, which replaces the script file."""
    if argument.startswith("--"):
        name = argument.partition("=")[0]
        return len(name) >= 3 and "--command".startswith(name)
    position = valued_letter(argument[1:])
    return position is not None and argument[1:][position] == "c"


def takes_next_word(argument: str) -> bool:
    """Whether the value of an option is the next word, not attached to it."""
    if argument.startswith("--"):
        return "=" not in argument and argument in VALUED_LONG_OPTIONS
    return valued_letter(argument[1:]) == len(argument) - 2


def valued_letter(letters: str) -> int | None:
    """The position of the first short option in a bundle that takes a value; the rest of the bundle is that value."""
    return next((position for position, letter in enumerate(letters) if letter in VALUED_LETTERS), None)
