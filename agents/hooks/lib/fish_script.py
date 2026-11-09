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
        if argument == "-" or replaces_file(argument):
            return None
        index += 2 if takes_next_word(argument) else 1
    return None


def replaces_file(argument: str) -> bool:
    """Whether the option leaves no file to run: -c or --command supplies the script, -n or --no-execute runs none.

    A long option may be abbreviated; a short one counts only in front of the value-taking letter of its bundle.
    """
    if argument.startswith("--"):
        name = argument.partition("=")[0]
        return (len(name) >= 3 and "--command".startswith(name)) or (
            len(name) >= 6 and "--no-execute".startswith(name)
        )
    letters = argument[1:]
    position = valued_letter(letters)
    return any(letter in "cn" for letter in (letters if position is None else letters[: position + 1]))


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
