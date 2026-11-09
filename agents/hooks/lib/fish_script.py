"""Find the script file a fish call runs, so its text can be read for what it would deny."""

from pathlib import Path

import shell_input
from shell_words import UnsupportedSyntax


# fish long options without a value; an abbreviation they share with a valued option is ambiguous.
FLAG_LONG_OPTIONS = frozenset(
    {
        "--no-config",
        "--no-execute",
        "--private",
        "--print-rusage-self",
        "--print-debug-categories",
        "--interactive",
        "--login",
        "--version",
        "--help",
    }
)
COMMAND, EXIT, NO_EXECUTE, INTERACTIVE = "command", "exit", "no-execute", "interactive"
SHORT_MEANINGS = {"c": COMMAND, "v": EXIT, "h": EXIT, "n": NO_EXECUTE, "i": INTERACTIVE}
# Each long option with what it means and the length of its shortest unambiguous abbreviation.
LONG_MEANINGS = (
    ("--command", COMMAND, 3),
    ("--version", EXIT, 3),
    ("--help", EXIT, 3),
    ("--print-debug-categories", EXIT, 9),
    ("--no-execute", NO_EXECUTE, 6),
    ("--interactive", INTERACTIVE, 5),
)
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
    index, seen = 1, set()
    while index < len(arguments) and arguments[index] != "--" and arguments[index].startswith("-"):
        if arguments[index] == "-":
            return None
        seen |= meanings(arguments[index])
        index += 2 if takes_next_word(arguments[index]) else 1
    index += index < len(arguments) and arguments[index] == "--"
    # fish drops -n when -i is given, and runs the file.
    runs_nothing = {COMMAND, EXIT} & seen or (NO_EXECUTE in seen and INTERACTIVE not in seen)
    return None if index >= len(arguments) or runs_nothing else index


def meanings(argument: str) -> set[str]:
    """What an option does to the file: supply a script, exit early, run nothing, or keep fish interactive.

    A long option may be abbreviated down to its shortest unambiguous form; a short one counts in front of
    the value-taking letter of its bundle.
    """
    if argument.startswith("--"):
        name = argument.partition("=")[0]
        return {
            meaning for option, meaning, shortest in LONG_MEANINGS if len(name) >= shortest and option.startswith(name)
        }
    letters = argument[1:]
    position = valued_letter(letters)
    return {
        SHORT_MEANINGS[letter]
        for letter in (letters if position is None else letters[: position + 1])
        if letter in SHORT_MEANINGS
    }


def takes_next_word(argument: str) -> bool:
    """Whether the value of an option is the next word, not attached to it."""
    if argument.startswith("--"):
        return "=" not in argument and is_valued_long_option(argument)
    return valued_letter(argument[1:]) == len(argument) - 2


def is_valued_long_option(name: str) -> bool:
    """Whether a long option, or an abbreviation that no other long option shares, takes a value."""
    return any(option.startswith(name) for option in VALUED_LONG_OPTIONS) and not any(
        option.startswith(name) for option in FLAG_LONG_OPTIONS
    )


def valued_letter(letters: str) -> int | None:
    """The position of the first short option in a bundle that takes a value; the rest of the bundle is that value."""
    return next((position for position, letter in enumerate(letters) if letter in VALUED_LETTERS), None)
