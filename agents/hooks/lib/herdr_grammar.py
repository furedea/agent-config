"""Judge Herdr's watching commands on their decoded words against the options each one documents.

Herdr strips global options such as --session before it parses a subcommand, so one anywhere in the
words can shift every value after it; a closed grammar refuses such words instead of reading past them.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

GLOBAL_OPTIONS = ("--session", "--machine", "--remote")
ValueRule = Callable[[str], bool]


def _any_word(value: str) -> bool:
    return not value.startswith("-")


def _number(value: str) -> bool:
    return value.isdigit()


def _one_of(*choices: str) -> ValueRule:
    return frozenset(choices).__contains__


@dataclass(frozen=True, slots=True)
class Form:
    """One subcommand's documented words: how many targets, valued options, and plain flags."""

    targets: int
    valued: dict[str, ValueRule]
    flags: frozenset[str] = frozenset()


FORMS = {
    ("agent", "read"): Form(
        1,
        {
            "--source": _one_of("visible", "recent", "recent-unwrapped", "detection"),
            "--lines": _number,
            "--format": _one_of("text", "ansi"),
        },
        frozenset({"--ansi"}),
    ),
    ("agent", "wait"): Form(1, {"--until": _any_word, "--timeout": _number}),
    ("worktree", "list"): Form(0, {"--workspace": _any_word, "--cwd": _any_word}),
    ("worktree", "open"): Form(
        0,
        dict.fromkeys(("--workspace", "--cwd", "--path", "--branch", "--label"), _any_word),
        frozenset({"--focus", "--no-focus"}),
    ),
}


def is_watch_command(arguments: tuple[str, ...]) -> bool:
    """Whether the words invoke a Herdr subcommand that has a documented form; `arguments` is non-empty."""
    return arguments[0] == "herdr" and tuple(arguments[1:3]) in FORMS


def has_global_option(arguments: tuple[str, ...]) -> bool:
    """Whether any word is a Herdr global option, bare or with `=value`, wherever it sits."""
    return any(word == option or word.startswith(f"{option}=") for word in arguments for option in GLOBAL_OPTIONS)


def is_documented(arguments: tuple[str, ...]) -> bool:
    """Whether a watching command uses only its documented options, each value a plain word."""
    rest = arguments[3:]
    if rest == ("--help",):
        return True
    form = FORMS[(arguments[1], arguments[2])]
    targets = 0
    words = iter(rest)
    for word in words:
        if not word.startswith("-"):
            targets += 1
        elif not _accepts(word, words, form):
            return False
    return targets == form.targets


def _accepts(option: str, words: Iterator[str], form: Form) -> bool:
    if option in form.flags:
        return True
    rule = form.valued.get(option)
    value = next(words, None)
    return rule is not None and value is not None and _any_word(value) and rule(value)
